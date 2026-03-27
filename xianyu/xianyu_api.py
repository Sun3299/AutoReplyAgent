"""
闲鱼API接口封装
统一管理所有与闲鱼服务器的REST API通信
"""
import time
import os
import re
import sys
from typing import Any, Dict, Optional
import requests
from loguru import logger

from .xianyu_utils import generate_sign


class XianyuAPIError(Exception):
    """API业务异常（非网络/系统错误）"""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class XianyuAuthError(XianyuAPIError):
    """认证失败（Cookie失效等）"""
    pass


class XianyuRiskControlError(XianyuAPIError):
    """触发风控"""
    pass


class XianyuAPI:
    """
    闲鱼API统一接口类

    包含以下API分组：
    - Auth: 登录状态、Token获取
    - Item: 商品信息查询
    """

    # API配置常量
    BASE_URL = 'https://h5api.m.goofish.com/h5'
    PASSPORT_URL = 'https://passport.goofish.com'
    APP_KEY = '34839810'
    APP_KEY_V2 = '444e9908a51d1cb236a27862abc769c9'

    # 默认请求头
    DEFAULT_HEADERS = {
        'accept': 'application/json',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'no-cache',
        'origin': 'https://www.goofish.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://www.goofish.com/',
        'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    # ==================== 公开API方法 ====================

    def has_login(self) -> bool:
        """
        检查登录状态

        Returns:
            bool: True-已登录，False-未登录
        """
        return self._has_login_impl() is True

    def get_token(self, device_id: str) -> Dict[str, Any]:
        """
        获取Access Token

        Args:
            device_id: 设备ID

        Returns:
            Dict包含 accessToken
        """
        return self._get_token_impl(device_id)

    def get_item_info(self, item_id: str) -> Dict[str, Any]:
        """
        获取商品详细信息

        Args:
            item_id: 商品ID

        Returns:
            Dict包含商品信息
        """
        return self._get_item_info_impl(item_id)

    # ==================== Cookie管理公开方法 ====================

    def set_cookies(self, cookies_str: str) -> None:
        """
        设置Cookie（支持字符串或字典）

        Args:
            cookies_str: Cookie字符串，格式如 "name1=value1; name2=value2"
        """
        cookies = self._parse_cookies(cookies_str)
        self.session.cookies.update(cookies)

    def get_cookies(self) -> str:
        """
        获取当前Cookie字符串

        Returns:
            Cookie字符串格式
        """
        return '; '.join([f"{c.name}={c.value}" for c in self.session.cookies])

    def sync_cookies_to_env(self, env_path: str = '.env') -> bool:
        """
        同步Cookie到.env文件

        Args:
            env_path: .env文件路径

        Returns:
            bool: 是否成功
        """
        return self._update_env_cookies(env_path)

    # ==================== 内部实现方法 ====================

    def _has_login_impl(self, retry_count: int = 0) -> bool:
        """登录状态检查实现"""
        if retry_count >= 2:
            logger.error("Login检查失败，重试次数过多")
            return False

        try:
            params = {
                'appName': 'xianyu',
                'fromSite': '77'
            }
            data = {
                'hid': self.session.cookies.get('unb', ''),
                'ltl': 'true',
                'appName': 'xianyu',
                'appEntrance': 'web',
                '_csrf_token': self.session.cookies.get('XSRF-TOKEN', ''),
                'umidToken': '',
                'hsiz': self.session.cookies.get('cookie2', ''),
                'bizParams': 'taobaoBizLoginFrom=web',
                'mainPage': 'false',
                'isMobile': 'false',
                'lang': 'zh_CN',
                'returnUrl': '',
                'fromSite': '77',
                'isIframe': 'true',
                'documentReferer': 'https://www.goofish.com/',
                'defaultView': 'hasLogin',
                'umidTag': 'SERVER',
                'deviceId': self.session.cookies.get('cna', '')
            }

            response = self.session.post(
                f'{self.PASSPORT_URL}/newlogin/hasLogin.do',
                params=params,
                data=data
            )
            res_json = response.json()

            if res_json.get('content', {}).get('success'):
                logger.debug("Login成功")
                self._clear_duplicate_cookies()
                return True
            else:
                logger.warning(f"Login失败: {res_json}")
                time.sleep(0.5)
                return self._has_login_impl(retry_count + 1)

        except Exception as e:
            logger.error(f"Login请求异常: {str(e)}")
            time.sleep(0.5)
            return self._has_login_impl(retry_count + 1)

    def _get_token_impl(self, device_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """获取Token实现"""
        if retry_count >= 2:
            logger.warning("获取token失败，尝试重新登陆")
            if self._has_login_impl():
                logger.info("重新登录成功，重新尝试获取token")
                return self._get_token_impl(device_id, 0)
            else:
                raise XianyuAuthError(
                    code='AUTH_EXPIRED',
                    message='重新登录失败，Cookie已失效，请更新.env文件中的COOKIES_STR'
                )

        params = self._build_mtop_params('mtop.taobao.idlemessage.pc.login.token')
        data_val = f'{{"appKey":"{self.APP_KEY_V2}","deviceId":"{device_id}"}}'

        response = self._do_mtop_request(
            endpoint='/mtop.taobao.idlemessage.pc.login.token/1.0/',
            params=params,
            data_val=data_val
        )

        res_json = response.json()
        ret_value = res_json.get('ret', [])
        if not any('SUCCESS::调用成功' in ret for ret in ret_value):
            error_msg = str(ret_value)

            # 检测风控
            if 'RGV587_ERROR' in error_msg or '被挤爆啦' in error_msg:
                logger.error(f"❌ 触发风控: {ret_value}")
                # 让用户输入新Cookie
                new_cookie_str = self._handle_risk_control_input()
                if new_cookie_str:
                    return self._get_token_impl(device_id, 0)
                else:
                    raise XianyuRiskControlError(
                        code='RISK_CONTROL',
                        message='风控处理取消，程序退出'
                    )

            # 处理Set-Cookie
            logger.warning(f"Token API调用失败: {ret_value}")
            # 检测并更新 Set-Cookie
            if 'Set-Cookie' in response.headers:
                logger.debug("检测到Set-Cookie，更新cookie")
                self._clear_duplicate_cookies()
            time.sleep(0.5)
            return self._get_token_impl(device_id, retry_count + 1)

        logger.info("Token获取成功")
        return res_json

    def _get_item_info_impl(self, item_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """获取商品信息实现"""
        if retry_count >= 3:
            raise XianyuAPIError(
                code='ITEM_INFO_FAILED',
                message='获取商品信息失败，重试次数过多'
            )

        params = self._build_mtop_params('mtop.taobao.idle.pc.detail')
        data_val = f'{{"itemId":"{item_id}"}}'

        response = self._do_mtop_request(
            endpoint='/mtop.taobao.idle.pc.detail/1.0/',
            params=params,
            data_val=data_val
        )

        res_json = response.json()
        ret_value = res_json.get('ret', [])
        if not any('SUCCESS::调用成功' in ret for ret in ret_value):
            logger.warning(f"商品信息API调用失败: {ret_value}")
            # 检测并更新 Set-Cookie
            if 'Set-Cookie' in response.headers:
                logger.debug("检测到Set-Cookie，更新cookie")
                self._clear_duplicate_cookies()
            time.sleep(0.5)
            return self._get_item_info_impl(item_id, retry_count + 1)

        logger.debug(f"商品信息获取成功: {item_id}")
        return res_json

    # ==================== 私有辅助方法 ====================

    def _build_mtop_params(self, api: str) -> Dict[str, str]:
        """构建MTOP API通用参数"""
        return {
            'jsv': '2.7.2',
            'appKey': self.APP_KEY,
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': api,
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
        }

    def _do_mtop_request(
        self,
        endpoint: str,
        params: Dict[str, str],
        data_val: str
    ) -> requests.Response:
        """执行MTOP API请求，返回原始响应对象"""
        # 获取token用于签名
        m_h5_tk = self.session.cookies.get('_m_h5_tk')
        token = (m_h5_tk if m_h5_tk else '').split('_')[0]

        # 生成签名
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        # 发送请求
        response = self.session.post(
            f'{self.BASE_URL}{endpoint}',
            params=params,
            data={'data': data_val}
        )

        return response

    def _parse_cookies(self, cookies_str: str) -> Dict[str, str]:
        """解析Cookie字符串为字典"""
        cookies = {}
        for cookie in cookies_str.split('; '):
            try:
                parts = cookie.split('=', 1)
                if len(parts) == 2:
                    cookies[parts[0]] = parts[1]
            except Exception:
                continue
        return cookies

    def _clear_duplicate_cookies(self) -> None:
        """清理重复的Cookie（保留最新的）"""
        new_jar = requests.cookies.RequestsCookieJar()  # type: ignore[attr-defined]
        added_cookies: set[str] = set()

        cookie_list = list(self.session.cookies)
        cookie_list.reverse()

        for cookie in cookie_list:
            cookie_name = getattr(cookie, 'name', None)  # type: ignore[arg-type]
            if cookie_name is None:
                cookie_name = str(cookie)
            if cookie_name not in added_cookies:
                new_jar.set_cookie(cookie)  # type: ignore[arg-type]
                added_cookies.add(cookie_name)

        self.session.cookies = new_jar

    def _update_env_cookies(self, env_path: str = '.env') -> bool:
        """更新.env文件中的COOKIES_STR"""
        try:
            cookie_str = self.get_cookies()
            env_path = os.path.join(os.getcwd(), env_path)

            if not os.path.exists(env_path):
                logger.warning(".env文件不存在，无法更新COOKIES_STR")
                return False

            with open(env_path, 'r', encoding='utf-8') as f:
                env_content = f.read()

            if 'COOKIES_STR=' in env_content:
                new_env_content = re.sub(
                    r'COOKIES_STR=.*',
                    f'COOKIES_STR={cookie_str}',
                    env_content
                )
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(new_env_content)
                logger.debug("已更新.env文件中的COOKIES_STR")
                return True
            else:
                logger.warning(".env文件中未找到COOKIES_STR配置项")
                return False

        except Exception as e:
            logger.warning(f"更新.env文件失败: {str(e)}")
            return False

    def _handle_risk_control_input(self) -> Optional[str]:
        """
        内部风控处理：提示用户手动输入新Cookie（供get_token内部调用）

        Returns:
            新Cookie字符串，或None（用户取消）
        """
        print("\n" + "=" * 50)
        print("🔴 触发风控，请进入闲鱼网页版 - 点击消息 - 过滑块 - 复制最新的Cookie")
        new_cookie_str = input("粘贴新Cookie（直接回车退出程序）: ").strip()
        print("=" * 50 + "\n")

        if not new_cookie_str:
            return None

        try:
            from http.cookies import SimpleCookie
            cookie = SimpleCookie()
            cookie.load(new_cookie_str)

            self.session.cookies.clear()
            for key, morsel in cookie.items():
                self.session.cookies.set(key, morsel.value, domain='.goofish.com')

            self._update_env_cookies()
            logger.info("✅ Cookie已更新，正在重试...")
            return new_cookie_str

        except Exception as e:
            logger.error(f"Cookie解析失败: {e}")
            return None

    # ==================== 风险控制处理（供外部调用） ====================

    def handle_risk_control(self) -> Optional[str]:
        """
        处理风控时调用此方法提示用户手动输入新Cookie

        Returns:
            新Cookie字符串，或None（用户取消）
        """
        return self._handle_risk_control_input()
