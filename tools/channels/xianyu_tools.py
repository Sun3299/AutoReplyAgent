"""
闲鱼平台工具

提供闲鱼专属的API调用工具。
"""

import sys
import os
from typing import Any, Dict, Optional

# 添加项目根目录到 path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.channels.base import BaseChannelTool, ToolResult


class XianyuItemTool(BaseChannelTool):
    """闲鱼商品信息查询工具"""
    
    def __init__(self):
        super().__init__("xianyu")
    
    @property
    def name(self) -> str:
        return "xianyu_item"
    
    @property
    def description(self) -> str:
        return "闲鱼商品信息查询工具，用于查询商品详情、价格、卖家信息等"
    
    def execute(self, **params) -> ToolResult:
        """
        查询闲鱼商品信息
        
        Args:
            item_id: 商品ID（必填）
            user_id: 用户ID（可选）
        """
        item_id = params.get("item_id")
        user_id = params.get("user_id")
        
        if not item_id:
            return ToolResult(
                success=False,
                error="缺少商品ID参数 item_id"
            )
        
        try:
            from xianyu.xianyu_api import XianyuAPI
            from dotenv import load_dotenv
            
            load_dotenv()
            
            api = XianyuAPI()
            cookies_str = os.getenv("COOKIES_STR", "")
            if cookies_str:
                api.set_cookies(cookies_str)
            
            result = api.get_item_info(item_id)
            
            return ToolResult(
                success=True,
                data=result,
                message="商品信息查询成功"
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"商品信息查询失败: {str(e)}"
            )


class XianyuSendMessageTool(BaseChannelTool):
    """闲鱼发送消息工具"""
    
    def __init__(self):
        super().__init__("xianyu")
    
    @property
    def name(self) -> str:
        return "xianyu_send_message"
    
    @property
    def description(self) -> str:
        return "闲鱼发送消息工具，用于向买家发送聊天消息"
    
    def execute(self, **params) -> ToolResult:
        """
        发送闲鱼消息
        
        Args:
            chat_id: 聊天会话ID（必填）
            content: 消息内容（必填）
            user_id: 用户ID（可选）
        """
        chat_id = params.get("chat_id")
        content = params.get("content")
        user_id = params.get("user_id")
        
        if not chat_id:
            return ToolResult(
                success=False,
                error="缺少聊天会话ID参数 chat_id"
            )
        
        if not content:
            return ToolResult(
                success=False,
                error="缺少消息内容参数 content"
            )
        
        try:
            from xianyu.main import XianyuLive
            
            # 获取单例实例
            try:
                xianyu_live = XianyuLive.get_instance()
            except ValueError:
                return ToolResult(
                    success=False,
                    error="XianyuLive未初始化，请先启动xianyu连接"
                )
            
            # 调用发送消息
            # chat_id 即 cid, user_id 即 toid
            result = xianyu_live.send_message_sync(
                cid=chat_id,
                toid=user_id or "",
                text=content
            )
            
            if result.get("success"):
                return ToolResult(
                    success=True,
                    data=result,
                    message="消息发送成功"
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.get("error", "发送失败")
                )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"消息发送失败: {str(e)}"
            )


def get_xianyu_tools():
    """获取所有闲鱼工具"""
    return {
        "xianyu_item": XianyuItemTool(),
        "xianyu_send_message": XianyuSendMessageTool(),
    }
