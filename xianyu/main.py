"""
闲鱼自动回复机器人 - 核心模块
功能说明：
1. 建立WebSocket连接，维持与闲鱼服务器的长连接
2. 自动处理用户消息，支持人工接管模式
3. 定时刷新Token，维持连接有效性
4. 心跳包机制保证连接稳定性
5. 支持商品信息解析、订单状态监控
6. 模拟人工输入延迟，提升回复真实性
"""
import base64
import json
import asyncio
import time
import os
import websockets
from loguru import logger
from dotenv import load_dotenv, set_key
from .xianyu_api import XianyuAPI  # 闲鱼API接口封装
import sys
import random
from typing import Dict

# 工具函数导入
from .xianyu_utils import generate_mid, generate_uuid, trans_cookies, generate_device_id, decrypt


class XianyuLive:
    """
    闲鱼WebSocket连接管理类
    负责：
    - WebSocket连接的建立、维持、重连
    - Token的获取与自动刷新
    - 心跳包发送与响应处理
    - 消息接收、解析、处理
    - 人工/自动模式切换
    
    单例模式：通过 get_instance() 获取实例
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls, cookies_str=None):
        """获取单例实例"""
        if cls._instance is None:
            if cookies_str is None:
                raise ValueError("首次调用需要提供 cookies_str")
            cls._instance = cls(cookies_str)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置单例（用于测试）"""
        cls._instance = None
    
    def __init__(self, cookies_str):
        """
        初始化闲鱼直播/聊天客户端

        Args:
            cookies_str (str): 闲鱼登录后的Cookie字符串
        """
        # 初始化API实例
        self.xianyu = XianyuAPI()
        # WebSocket基础连接地址
        self.base_url = 'wss://wss-goofish.dingtalk.com/'
        # 原始Cookie字符串
        self.cookies_str = cookies_str
        # 转换Cookie为字典格式
        self.cookies = trans_cookies(cookies_str)
        # 更新API会话的Cookie
        self.xianyu.session.cookies.update(self.cookies)
        # 从Cookie中获取用户ID
        self.myid = self.cookies['unb']
        # 生成设备ID
        self.device_id = generate_device_id(self.myid)
        # ==================== Session 缓存 ====================
        # 缓存商品信息，key=chat_id, value=item_info
        self.session_item_cache: Dict[str, Dict] = {}
        # ==================== 商品信息缓存 ====================
        # 按商品缓存，key=item_id, value=item_info，避免重复调用API
        self.item_info_cache: Dict[str, Dict] = {}

        # ==================== 心跳相关配置 ====================
        # 心跳发送间隔（秒），默认15秒
        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "15"))
        # 心跳超时时间（秒），默认5秒
        self.heartbeat_timeout = int(os.getenv("HEARTBEAT_TIMEOUT", "5"))
        # 上次发送心跳时间戳
        self.last_heartbeat_time = 0
        # 上次收到心跳响应时间戳
        self.last_heartbeat_response = 0
        # 心跳任务对象
        self.heartbeat_task = None
        # WebSocket连接对象
        self.ws = None

        # ==================== Token刷新相关配置 ====================
        # Token刷新间隔（秒），默认1小时(3600秒)
        self.token_refresh_interval = int(os.getenv("TOKEN_REFRESH_INTERVAL", "86400"))
        # Token刷新失败后重试间隔（秒），默认5分钟(300秒)
        self.token_retry_interval = int(os.getenv("TOKEN_RETRY_INTERVAL", "300"))
        # 上次Token刷新时间戳
        self.last_token_refresh_time = 0
        # 当前有效的Token
        self.current_token = None
        # Token刷新任务对象
        self.token_refresh_task = None
        # 连接重启标志（Token刷新后需要重启连接）
        self.connection_restart_flag = False

        # ==================== 人工接管相关配置 ====================
        # 存储处于人工接管模式的会话ID集合
        self.manual_mode_conversations = set()
        # 人工接管超时时间（秒），默认1小时(3600秒)
        self.manual_mode_timeout = int(os.getenv("MANUAL_MODE_TIMEOUT", "3600"))
        # 记录进入人工模式的时间戳 {chat_id: timestamp}
        self.manual_mode_timestamps = {}

        # ==================== 消息过滤相关配置 ====================
        # 消息过期时间（毫秒），默认5分钟(300000毫秒)
        self.message_expire_time = int(os.getenv("MESSAGE_EXPIRE_TIME", "300000"))

        # ==================== 模式切换配置 ====================
        # 人工/自动模式切换关键词，从环境变量读取
        self.toggle_keywords = os.getenv("TOGGLE_KEYWORDS", "。")

        # ==================== 模拟人工输入配置 ====================
        # 是否模拟人工打字延迟
        self.simulate_human_typing = os.getenv("SIMULATE_HUMAN_TYPING", "False").lower() == "true"

        # ==================== 消息追踪 ====================
        # 上次收到业务消息时间（用于保活）
        self.last_message_time = time.time()
        # 保活消息发送间隔（秒），默认3分钟
        self.keepalive_interval = int(os.getenv("KEEPALIVE_INTERVAL", "180"))

        # ==================== 测试配置 ====================
        # 是否禁用 Token 自动刷新（用于测试 Token 实际过期时间）
        # 设为 true 时不会主动刷新，等 Token 自然过期
        self.disable_token_refresh = os.getenv("DISABLE_TOKEN_REFRESH", "false").lower() == "true"

    async def refresh_token(self):
        """
        刷新Access Token
        Returns:
            str | None: 新的Token，失败返回None
        """
        try:
            logger.info("开始刷新token...")

            # 调用API获取新Token（Cookie失效时get_token会直接退出程序）
            token_result = self.xianyu.get_token(self.device_id)

            # 检查Token获取结果
            if 'data' in token_result and 'accessToken' in token_result['data']:
                new_token = token_result['data']['accessToken']
                self.current_token = new_token
                self.last_token_refresh_time = time.time()
                logger.info("Token刷新成功")
                return new_token
            else:
                logger.error(f"Token刷新失败: {token_result}")
                return None

        except Exception as e:
            logger.error(f"Token刷新异常: {str(e)}")
            return None

    async def token_refresh_loop(self):
        """
        Token自动刷新循环任务
        每分钟检查一次Token有效期，到期自动刷新并重启连接
        """
        while True:
            try:
                current_time = time.time()

                # 检查是否需要刷新Token（当前时间 - 上次刷新时间 >= 刷新间隔）
                if current_time - self.last_token_refresh_time >= self.token_refresh_interval:
                    # 检查是否禁用了 Token 刷新（用于测试）
                    if self.disable_token_refresh:
                        logger.info("【测试模式】Token刷新已禁用，等待自然过期...")
                        # 不刷新，只等，然后继续检查
                        await asyncio.sleep(60)
                        continue

                    logger.info("Token即将过期，准备刷新...")

                    # 尝试刷新Token
                    new_token = await self.refresh_token()
                    if new_token:
                        logger.info("Token刷新成功，准备重新建立连接...")
                        # 设置连接重启标志
                        self.connection_restart_flag = True
                        # 关闭当前WebSocket连接，触发重连逻辑
                        if self.ws:
                            await self.ws.close()
                        break  # 退出当前循环，主循环会重新建立连接
                    else:
                        retry_minutes = self.token_retry_interval // 60
                        logger.error(f"Token刷新失败，将在{retry_minutes}分钟后重试")
                        await asyncio.sleep(self.token_retry_interval)
                        continue

                # 每分钟检查一次Token状态
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Token刷新循环出错: {e}")
                await asyncio.sleep(60)

    async def send_msg(self, ws, cid, toid, text):
        """
        发送消息到指定会话

        Args:
            ws (websockets.WebSocketClientProtocol): WebSocket连接对象
            cid (str): 会话ID
            toid (str): 接收方用户ID
            text (str): 要发送的文本消息
        """
        # 构建消息体结构
        text_payload = {
            "contentType": 1,  # 文本类型
            "text": {
                "text": text
            }
        }

        # Base64编码消息内容
        text_base64 = str(base64.b64encode(json.dumps(text_payload).encode('utf-8')), 'utf-8')

        # 构建完整的发送消息结构
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",  # 消息发送接口
            "headers": {
                "mid": generate_mid()  # 生成消息ID
            },
            "body": [
                {
                    "uuid": generate_uuid(),  # 生成UUID
                    "cid": f"{cid}@goofish",  # 完整会话ID
                    "conversationType": 1,  # 单聊类型
                    "content": {
                        "contentType": 101,  # 自定义内容类型
                        "custom": {
                            "type": 1,
                            "data": text_base64  # Base64编码的消息内容
                        }
                    },
                    "redPointPolicy": 0,  # 红点策略
                    "extension": {
                        "extJson": "{}"  # 扩展字段
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1  # 消息已读设置
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",  # 接收方
                        f"{self.myid}@goofish"  # 发送方（自己）
                    ]
                }
            ]
        }

        # 发送消息
        await ws.send(json.dumps(msg))

    def send_message_sync(self, cid: str, toid: str, text: str) -> dict:
        """
        同步发送消息（供 Tool 调用）
        
        将消息放入队列，由事件循环异步发送。
        
        Args:
            cid: 会话ID
            toid: 接收方用户ID
            text: 消息内容
            
        Returns:
            dict: 发送结果
        """
        import threading
        
        if self.ws is None:
            return {"success": False, "error": "WebSocket未连接"}
        
        # 如果已经在事件循环中，直接发送
        try:
            loop = asyncio.get_running_loop()
            # 创建任务放入事件循环
            future = asyncio.run_coroutine_threadsafe(
                self.send_msg(self.ws, cid, toid, text),
                loop
            )
            try:
                future.result(timeout=10)
                return {"success": True, "cid": cid, "toid": toid, "text": text}
            except Exception as e:
                return {"success": False, "error": str(e)}
        except RuntimeError:
            # 没有运行中的事件循环
            return {"success": False, "error": "事件循环未运行，请先启动连接"}

    async def init(self, ws):
        """
        初始化WebSocket连接
        发送注册消息和同步状态，完成连接初始化

        Args:
            ws (websockets.WebSocketClientProtocol): WebSocket连接对象

        Raises:
            Exception: Token获取失败时抛出异常
        """
        # 检查并获取初始Token
        if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
            logger.info("获取初始token...")
            await self.refresh_token()

        # 验证Token有效性
        if not self.current_token:
            logger.error("无法获取有效token，初始化失败")
            raise Exception("Token获取失败")

        # 构建注册消息
        reg_msg = {
            "lwp": "/reg",  # 注册接口
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",  # 固定APP KEY
                "token": self.current_token,  # 访问令牌
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",  # 数据类型
                "wv": "im:3,au:3,sy:6",  # 版本信息
                "sync": "0,0;0;0;",  # 同步参数
                "did": self.device_id,  # 设备ID
                "mid": generate_mid()  # 消息ID
            }
        }

        # 发送注册消息
        await ws.send(json.dumps(reg_msg))

        # 等待1秒确保注册完成
        await asyncio.sleep(1)

        # 发送同步状态确认消息
        sync_msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": "5701741704675979 0"},
            "body": [{
                "pipeline": "sync",
                "tooLong2Tag": "PNM,1",
                "channel": "sync",
                "topic": "sync",
                "highPts": 0,
                "pts": int(time.time() * 1000) * 1000,  # 时间戳（微秒）
                "seq": 0,
                "timestamp": int(time.time() * 1000)  # 时间戳（毫秒）
            }]
        }

        await ws.send(json.dumps(sync_msg))
        logger.info('连接注册完成')

    def is_chat_message(self, message):
        """
        判断是否为用户聊天消息

        Args:
            message (dict): 解析后的消息字典

        Returns:
            bool: True-是聊天消息，False-不是
        """
        try:
            return (
                    isinstance(message, dict)
                    and "1" in message
                    and isinstance(message["1"], dict)
                    and "10" in message["1"]
                    and isinstance(message["1"]["10"], dict)
                    and "reminderContent" in message["1"]["10"]  # 消息内容字段存在
            )
        except Exception:
            return False

    def is_sync_package(self, message_data):
        """
        判断是否为同步包消息（包含用户聊天、订单等核心数据）

        Args:
            message_data (dict): WebSocket原始消息数据

        Returns:
            bool: True-是同步包，False-不是
        """
        try:
            return (
                    isinstance(message_data, dict)
                    and "body" in message_data
                    and "syncPushPackage" in message_data["body"]
                    and "data" in message_data["body"]["syncPushPackage"]
                    and len(message_data["body"]["syncPushPackage"]["data"]) > 0
            )
        except Exception:
            return False

    def is_typing_status(self, message):
        """
        判断是否为用户正在输入状态的消息

        Args:
            message (dict): 解析后的消息字典

        Returns:
            bool: True-正在输入，False-不是
        """
        try:
            return (
                    isinstance(message, dict)
                    and "1" in message
                    and isinstance(message["1"], list)
                    and len(message["1"]) > 0
                    and isinstance(message["1"][0], dict)
                    and "1" in message["1"][0]
                    and isinstance(message["1"][0]["1"], str)
                    and "@goofish" in message["1"][0]["1"]  # 包含用户ID标识
            )
        except Exception:
            return False

    def is_system_message(self, message):
        """
        判断是否为系统消息

        Args:
            message (dict): 解析后的消息字典

        Returns:
            bool: True-系统消息，False-不是
        """
        try:
            return (
                    isinstance(message, dict)
                    and "3" in message
                    and isinstance(message["3"], dict)
                    and "needPush" in message["3"]
                    and message["3"]["needPush"] == "false"  # 系统消息无需推送
            )
        except Exception:
            return False

    def is_bracket_system_message(self, message):
        """
        检查是否为带中括号的系统消息（如：[对方已读]、[对方正在输入]等）

        Args:
            message (str): 消息文本内容

        Returns:
            bool: True-是系统消息，False-不是
        """
        try:
            if not message or not isinstance(message, str):
                return False

            clean_message = message.strip()
            # 检查是否以 [ 开头且以 ] 结尾
            if clean_message.startswith('[') and clean_message.endswith(']'):
                logger.debug(f"检测到系统消息: {clean_message}")
                return True
            return False
        except Exception as e:
            logger.error(f"检查系统消息失败: {e}")
            return False

    def check_toggle_keywords(self, message):
        """
        检查消息是否包含人工/自动模式切换关键词

        Args:
            message (str): 消息文本

        Returns:
            bool: True-包含切换关键词，False-不包含
        """
        message_stripped = message.strip()
        return message_stripped in self.toggle_keywords

    def is_manual_mode(self, chat_id):
        """
        检查特定会话是否处于人工接管模式

        Args:
            chat_id (str): 会话ID

        Returns:
            bool: True-人工模式，False-自动模式
        """
        # 不在人工模式集合中，直接返回False
        if chat_id not in self.manual_mode_conversations:
            return False

        # 检查人工模式是否超时
        current_time = time.time()
        if chat_id in self.manual_mode_timestamps:
            if current_time - self.manual_mode_timestamps[chat_id] > self.manual_mode_timeout:
                # 超时自动退出人工模式
                self.exit_manual_mode(chat_id)
                return False

        return True

    def enter_manual_mode(self, chat_id):
        """
        进入人工接管模式

        Args:
            chat_id (str): 会话ID
        """
        self.manual_mode_conversations.add(chat_id)
        self.manual_mode_timestamps[chat_id] = time.time()

    def exit_manual_mode(self, chat_id):
        """
        退出人工接管模式

        Args:
            chat_id (str): 会话ID
        """
        self.manual_mode_conversations.discard(chat_id)
        if chat_id in self.manual_mode_timestamps:
            del self.manual_mode_timestamps[chat_id]

    def toggle_manual_mode(self, chat_id):
        """
        切换人工/自动接管模式

        Args:
            chat_id (str): 会话ID

        Returns:
            str: "manual"-切换到人工模式，"auto"-切换到自动模式
        """
        if self.is_manual_mode(chat_id):
            self.exit_manual_mode(chat_id)
            return "auto"
        else:
            self.enter_manual_mode(chat_id)
            return "manual"

    def format_price(self, price):
        """
        价格格式化：分转元，保留两位小数

        Args:
            price (str | int | float): 价格（单位：分）

        Returns:
            float: 格式化后的价格（单位：元）
        """
        try:
            return round(float(price) / 100, 2)
        except (ValueError, TypeError):
            # 处理异常值，默认返回0
            return 0.0

    def build_item_description(self, item_info):
        """
        构建商品描述信息

        Args:
            item_info (dict): 原始商品信息字典

        Returns:
            str: JSON格式的商品描述字符串
        """
        # 处理SKU列表
        clean_skus = []
        raw_sku_list = item_info.get('skuList', [])

        for sku in raw_sku_list:
            # 提取规格文本
            specs = [p['valueText'] for p in sku.get('propertyList', []) if p.get('valueText')]
            spec_text = " ".join(specs) if specs else "默认规格"

            # 构建SKU信息
            clean_skus.append({
                "spec": spec_text,  # 规格描述
                "price": self.format_price(sku.get('price', 0)),  # 价格（元）
                "stock": sku.get('quantity', 0)  # 库存
            })

        # 计算价格区间
        valid_prices = [s['price'] for s in clean_skus if s['price'] > 0]

        if valid_prices:
            min_price = min(valid_prices)
            max_price = max(valid_prices)
            if min_price == max_price:
                price_display = f"¥{min_price}"
            else:
                price_display = f"¥{min_price} - ¥{max_price}"
        else:
            # 无SKU价格时使用商品主价格
            main_price = round(float(item_info.get('soldPrice', 0)), 2)
            price_display = f"¥{main_price}"

        # 构建商品摘要
        summary = {
            "title": item_info.get('title', ''),  # 商品标题
            "desc": item_info.get('desc', ''),  # 商品描述
            "price_range": price_display,  # 价格区间
            "total_stock": item_info.get('quantity', 0),  # 总库存
            "sku_details": clean_skus  # SKU详情
        }

        return json.dumps(summary, ensure_ascii=False)

    async def handle_message(self, message_data, websocket):
        """
        处理接收到的所有消息

        Args:
            message_data (dict): WebSocket原始消息数据
            websocket (websockets.WebSocketClientProtocol): WebSocket连接对象
        """
        try:
            # ==================== 发送通用ACK响应 ====================
            try:
                message = message_data
                # 构建ACK响应
                ack = {
                    "code": 200,  # 成功响应码
                    "headers": {
                        "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                        "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                    }
                }

                # 复制必要的header字段
                for key in ["app-key", "ua", "dt"]:
                    if key in message["headers"]:
                        ack["headers"][key] = message["headers"][key]

                await websocket.send(json.dumps(ack))
            except Exception as e:
                logger.debug(f"发送ACK响应失败: {e}")

            # ==================== 过滤非同步包消息 ====================
            if not self.is_sync_package(message_data):
                return

            # ==================== 解密消息内容 ====================
            sync_data = message_data["body"]["syncPushPackage"]["data"][0]

            # 检查data字段是否存在
            if "data" not in sync_data:
                logger.debug("同步包中无data字段")
                return

            # 解密数据（先尝试Base64解码，失败则使用自定义解密）
            try:
                data = sync_data["data"]
                try:
                    # 尝试直接Base64解码
                    data = base64.b64decode(data).decode("utf-8")
                    data = json.loads(data)
                    return
                except Exception:
                    # 使用自定义解密方法
                    decrypted_data = decrypt(data)
                    message = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"消息解密失败: {e}")
                return

            # ==================== 处理订单状态消息 ====================
            try:
                # 订单状态判断（等待付款、交易关闭、等待发货）
                red_reminder = message['3']['redReminder']
                if red_reminder == '等待买家付款':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'等待买家 {user_url} 付款')
                    return
                elif red_reminder == '交易关闭':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'买家 {user_url} 交易关闭')
                    return
                elif red_reminder == '等待卖家发货':
                    user_id = message['1'].split('@')[0]
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'交易成功 {user_url} 等待卖家发货')
                    return
            except Exception:
                # 非订单消息，继续处理
                pass

            # ==================== 过滤非聊天消息 ====================
            if self.is_typing_status(message):
                logger.debug("用户正在输入")
                return
            elif not self.is_chat_message(message):
                logger.debug("其他非聊天消息")
                logger.debug(f"原始消息: {message}")
                return

            # ==================== 解析聊天消息 ====================
            # 消息创建时间（毫秒）
            create_time = int(message["1"]["5"])
            # 发送者昵称
            send_user_name = message["1"]["10"]["reminderTitle"]
            # 发送者ID
            send_user_id = message["1"]["10"]["senderUserId"]
            # 消息内容
            send_message = message["1"]["10"]["reminderContent"]

            # ==================== 过滤过期消息 ====================
            if (time.time() * 1000 - create_time) > self.message_expire_time:
                logger.debug("过期消息丢弃")
                return

            # ==================== 提取商品和会话信息 ====================
            # 从URL中提取商品ID
            url_info = message["1"]["10"]["reminderUrl"]
            item_id = url_info.split("itemId=")[1].split("&")[0] if "itemId=" in url_info else None
            # 提取会话ID
            chat_id = message["1"]["2"].split('@')[0]

            if not item_id:
                logger.warning("无法获取商品ID")
                return

            # ==================== 处理卖家控制命令 ====================
            if send_user_id == self.myid:
                logger.debug("检测到卖家消息，检查是否为控制命令")

                # 检查模式切换命令
                if self.check_toggle_keywords(send_message):
                    mode = self.toggle_manual_mode(chat_id)
                    if mode == "manual":
                        logger.info(f"🔴 已接管会话 {chat_id} (商品: {item_id})")
                    else:
                        logger.info(f"🟢 已恢复会话 {chat_id} 的自动回复 (商品: {item_id})")
                    return

                # 记录卖家人工回复
                logger.info(f"卖家人工回复 (会话: {chat_id}, 商品: {item_id}): {send_message}")
                return

            # ==================== 记录用户消息 ====================
            logger.info(
                f"用户: {send_user_name} (ID: {send_user_id}), 商品: {item_id}, 会话: {chat_id}, 消息: {send_message}")
            
            # 更新最后消息时间（用于保活）
            self.last_message_time = time.time()

            # ==================== 人工模式检查 ====================
            if self.is_manual_mode(chat_id):
                logger.info(f"🔴 会话 {chat_id} 处于人工接管模式，跳过自动回复")
                return

            # ==================== 过滤系统消息 ====================
            if self.is_bracket_system_message(send_message):
                logger.info(f"检测到系统消息：'{send_message}'，跳过自动回复")
                return

            if self.is_system_message(message):
                logger.debug("系统消息，跳过处理")
                return

            # ==================== 获取商品信息（按商品缓存）====================
            item_description = ""
            if item_id not in self.item_info_cache:
                # 新商品，获取并缓存商品信息
                logger.info(f"新商品，从API获取商品信息: {item_id}")
                api_result = self.xianyu.get_item_info(item_id)
                if 'data' in api_result and 'itemDO' in api_result['data']:
                    item_info = api_result['data']['itemDO']
                    self.item_info_cache[item_id] = item_info
                    item_description = f"当前商品的信息如下：{self.build_item_description(item_info)}"
                    logger.info(f"【商品缓存】商品信息已缓存，商品 {item_id}")
                else:
                    logger.warning(f"获取商品信息失败: {api_result}")
            else:
                # 老商品，用缓存
                cached_item = self.item_info_cache.get(item_id, {})
                item_description = f"当前商品的信息如下：{self.build_item_description(cached_item)}"
                logger.debug(f"【商品缓存命中】使用缓存的商品信息，商品 {item_id}")

            # ==================== 调用 autoreply ====================
            logger.info(f"调用autoreply API，会话: {chat_id}")
            try:
                import requests
                import time as time_module
                
                # 构建请求
                autoreply_payload = {
                    "requestId": f"xianyu_{generate_mid()}",
                    "userId": str(send_user_id),
                    "channel": "xianyu",
                    "sessionId": str(chat_id),
                    "sessionKey": str(chat_id),
                    "msgType": "text",
                    "content": send_message,
                    "createTime": time_module.strftime("%Y-%m-%d %H:%M:%S"),
                    "extension": {
                        "item_id": str(item_id),
                        "item_info": item_description,
                    }
                }
                
                logger.info(f"【AUTOREPLY请求】{json.dumps(autoreply_payload, ensure_ascii=False)}")
                
                # 调用 autoreply
                resp = requests.post(
                    "http://localhost:8000/v1/chat",
                    json=autoreply_payload,
                    timeout=60
                )
                
                if resp.status_code == 200:
                    result = resp.json()
                    ai_reply = result.get("content", "")
                    logger.info(f"【AUTOREPLY响应】{ai_reply[:100]}")
                    
                    # 发送回复
                    if ai_reply:
                        await self.send_msg(self.ws, chat_id, send_user_id, ai_reply)
                        self.last_message_time = time.time()  # 更新最后消息时间（发送也算活动）
                        logger.info(f"【已发送回复】到会话 {chat_id}: {ai_reply[:50]}...")
                    else:
                        logger.warning(f"【AUTOREPLY返回空】会话 {chat_id}")
                else:
                    logger.error(f"【AUTOREPLY失败】状态码: {resp.status_code}")
                    
            except Exception as e:
                logger.error(f"【AUTOREPLY异常】{str(e)}")

        except Exception as e:
            logger.error(f"处理消息时发生错误: {str(e)}")
            logger.debug(f"原始消息: {message_data}")

    async def send_heartbeat(self, ws):
        """
        发送心跳包

        Args:
            ws (websockets.WebSocketClientProtocol): WebSocket连接对象

        Returns:
            str: 心跳包的mid

        Raises:
            Exception: 发送失败时抛出异常
        """
        try:
            heartbeat_mid = generate_mid()
            heartbeat_msg = {
                "lwp": "/!",  # 心跳接口标识
                "headers": {
                    "mid": heartbeat_mid
                }
            }
            await ws.send(json.dumps(heartbeat_msg))
            self.last_heartbeat_time = time.time()
            logger.debug("心跳包已发送")
            return heartbeat_mid
        except Exception as e:
            logger.error(f"发送心跳包失败: {e}")
            raise

    async def heartbeat_loop(self, ws):
        """
        心跳维护循环
        定时发送心跳包，检查心跳响应超时，发送保活消息防止连接被服务器关闭

        Args:
            ws (websockets.WebSocketClientProtocol): WebSocket连接对象
        """
        while True:
            try:
                current_time = time.time()

                # 检查是否需要发送心跳
                if current_time - self.last_heartbeat_time >= self.heartbeat_interval:
                    await self.send_heartbeat(ws)

                # 检查保活：如果超过3分钟没有收到任何消息，发送ping保持连接
                if current_time - self.last_message_time >= self.keepalive_interval:
                    try:
                        # 使用 WebSocket 协议的 ping 帧保活
                        await ws.ping()
                        logger.debug(f"发送保活ping，距离上次消息已过 {int(current_time - self.last_message_time)} 秒")
                    except Exception as e:
                        logger.warning(f"保活ping失败: {e}")
                        break

                # 检查心跳响应超时
                if (current_time - self.last_heartbeat_response) > (self.heartbeat_interval + self.heartbeat_timeout):
                    logger.warning("心跳响应超时，可能连接已断开")
                    break

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"心跳循环出错: {e}")
                break

    async def handle_heartbeat_response(self, message_data):
        """
        处理心跳响应消息

        Args:
            message_data (dict): WebSocket消息数据

        Returns:
            bool: True-是心跳响应，False-不是
        """
        try:
            if (
                    isinstance(message_data, dict)
                    and "headers" in message_data
                    and "mid" in message_data["headers"]
                    and "code" in message_data
                    and message_data["code"] == 200  # 成功响应码
            ):
                self.last_heartbeat_response = time.time()
                logger.debug("收到心跳响应")
                return True
        except Exception as e:
            logger.error(f"处理心跳响应出错: {e}")
        return False

    async def main(self):
        """
        主循环：建立WebSocket连接，处理消息，自动重连
        """
        while True:
            try:
                # 重置连接重启标志
                self.connection_restart_flag = False

                # 构建WebSocket连接头
                headers = {
                    "Cookie": self.cookies_str,
                    "Host": "wss-goofish.dingtalk.com",
                    "Connection": "Upgrade",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache",
                    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36 Edg/146.0.0.0",
                    "Origin": "https://www.goofish.com",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }

                # 建立WebSocket连接（传入headers）
                async with websockets.connect(self.base_url, additional_headers=headers) as websocket:
                    self.ws = websocket
                    # 初始化连接
                    await self.init(websocket)

                    # 初始化心跳时间
                    self.last_heartbeat_time = time.time()
                    self.last_heartbeat_response = time.time()
                    self.last_message_time = time.time()

                    # 启动心跳任务
                    self.heartbeat_task = asyncio.create_task(self.heartbeat_loop(websocket))

                    # 启动Token刷新任务
                    self.token_refresh_task = asyncio.create_task(self.token_refresh_loop())

                    # 持续接收消息
                    async for message in websocket:
                        try:
                            # 检查是否需要重启连接（Token刷新后）
                            if self.connection_restart_flag:
                                logger.info("检测到连接重启标志，准备重新建立连接...")
                                break

                            # 解析JSON消息
                            message_data = json.loads(message)

                            # 处理心跳响应
                            if await self.handle_heartbeat_response(message_data):
                                continue

                            # 发送通用ACK响应
                            if "headers" in message_data and "mid" in message_data["headers"]:
                                ack = {
                                    "code": 200,
                                    "headers": {
                                        "mid": message_data["headers"]["mid"],
                                        "sid": message_data["headers"].get("sid", "")
                                    }
                                }
                                # 复制必要的header字段
                                for key in ["app-key", "ua", "dt"]:
                                    if key in message_data["headers"]:
                                        ack["headers"][key] = message_data["headers"][key]
                                await websocket.send(json.dumps(ack))

                            # 处理业务消息
                            await self.handle_message(message_data, websocket)

                        except json.JSONDecodeError:
                            logger.error("消息解析失败")
                        except Exception as e:
                            logger.error(f"处理消息时发生错误: {str(e)}")
                            logger.debug(f"原始消息: {message}")

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket连接已关闭")

            except Exception as e:
                logger.error(f"连接发生错误: {e}")

            finally:
                # 清理心跳任务
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    try:
                        await self.heartbeat_task
                    except asyncio.CancelledError:
                        pass

                # 清理Token刷新任务
                if self.token_refresh_task:
                    self.token_refresh_task.cancel()
                    try:
                        await self.token_refresh_task
                    except asyncio.CancelledError:
                        pass

                # 重连策略：主动重启立即重连，否则等待5秒
                if self.connection_restart_flag:
                    logger.info("主动重启连接，立即重连...")
                else:
                    logger.info("等待5秒后重连...")
                    await asyncio.sleep(5)


def check_and_complete_env():
    """
    检查并交互式补全关键环境变量
    确保COOKIES_STR和API_KEY等关键配置已正确设置
    """
    # 定义关键环境变量及其说明
    critical_vars = {
        "API_KEY": "默认使用通义千问,apikey通过百炼模型平台获取",
        "COOKIES_STR": "your_cookies_here"
    }

    env_path = ".env"
    updated = False

    for key, placeholder in critical_vars.items():
        curr_val = os.getenv(key)

        # 检查变量是否未设置或为默认占位符
        if not curr_val or curr_val == placeholder:
            logger.warning(f"配置项 [{key}] 未设置或为默认值，请输入")
            while True:
                val = input(f"请输入 {key}: ").strip()
                if val:
                    # 更新当前进程环境变量
                    os.environ[key] = val

                    # 持久化到.env文件
                    try:
                        # 如果.env文件不存在则创建
                        if not os.path.exists(env_path):
                            with open(env_path, 'w', encoding='utf-8') as f:
                                pass

                        # 更新.env文件中的变量
                        set_key(env_path, key, val)
                        updated = True
                    except Exception as e:
                        logger.warning(f"无法自动写入.env文件，请手动保存: {e}")
                    break
                else:
                    print(f"{key} 不能为空，请重新输入")

    if updated:
        logger.info("新的配置已保存/更新至 .env 文件中")


if __name__ == '__main__':
    """
    程序入口
    1. 加载环境变量
    2. 配置日志
    3. 检查必要配置
    4. 启动主程序
    """
    # 加载环境变量
    if os.path.exists(".env"):
        load_dotenv()
        logger.info("已加载 .env 配置")

    if os.path.exists(".env.example"):
        load_dotenv(".env.example")  # 加载示例配置（不会覆盖已存在的变量）
        logger.info("已加载 .env.example 默认配置")

    # 配置日志系统
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    logger.remove()  # 移除默认处理器
    # 添加自定义日志格式
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.info(f"日志级别设置为: {log_level}")

    # 交互式检查并补全配置
    check_and_complete_env()

    # 初始化核心组件
    cookies_str = os.getenv("COOKIES_STR")
    xianyuLive = XianyuLive(cookies_str)

    # 启动异步主程序
    asyncio.run(xianyuLive.main())