"""
获取外部信息工具

统一封装不同平台的外部信息获取能力：
- 订单查询
- 物流查询
- 退款状态
- 用户信息
- 转人工

设计思想：
- 原子化：只提供一个工具，具体怎么用由 LLM 决定
- 动态编排：工具层不关心"什么场景用什么"，只提供"有什么"
- 可插拔：具体平台实现通过 PlatformAdapter 注册

使用方式：
1. 注册平台适配器
2. 调用工具
3. 场景判断和工具编排由上层 Agent + LLM 决定

具体平台实现待定，由 PlatformAdapter 注册。
"""

from abc import ABC, abstractmethod

from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from .base import BaseTool, ToolResult, ToolType


class InfoType(Enum):
    """
    信息类型枚举
    
    定义外部信息查询的类型：
    - ORDER: 订单查询
    - LOGISTICS: 物流查询
    - REFUND: 退款查询
    - USER: 用户信息
    - TRANSFER_HUMAN: 转人工客服
    """
    ORDER = "order"                 # 订单查询
    LOGISTICS = "logistics"         # 物流查询
    REFUND = "refund"              # 退款查询
    USER = "user"                  # 用户信息
    TRANSFER_HUMAN = "transfer_human"  # 转人工


@dataclass
class ExternalInfoRequest:
    """
    外部信息请求
    
    当需要调用外部平台接口时，构造此请求。
    
    Attributes:
        info_type: 信息类型
        params: 查询参数
        platform: 指定平台（可选，None表示自动选择）
    """
    info_type: InfoType              # 信息类型
    params: Dict[str, Any] = field(default_factory=dict)  # 查询参数
    platform: Optional[str] = None   # 平台标识


@dataclass
class ExternalInfoResponse:
    """
    外部信息响应
    
    平台适配器返回的统一响应格式。
    
    Attributes:
        success: 是否成功
        data: 返回数据
        platform: 数据来源平台
        message: 提示信息
    """
    success: bool                        # 是否成功
    data: Optional[Any] = None          # 返回数据
    platform: str = "unknown"           # 来源平台
    message: str = ""                  # 提示信息


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类
    
    每个外部平台（如某宝、某东、某多多）实现此接口。
    通过适配器模式，统一不同平台的接口差异。
    
    实现要求：
    - 实现 get_name() 返回平台唯一标识
    - 实现各查询方法，返回 ExternalInfoResponse
    - 处理平台特定的错误，如 API 限流、认证失败等
    
    使用示例：
        class TaobaoAdapter(PlatformAdapter):
            def get_name(self) -> str:
                return "taobao"
            
            def query_order(self, order_id: str) -> ExternalInfoResponse:
                # 调用淘宝订单 API
                return ExternalInfoResponse(
                    success=True,
                    data={"order_id": order_id, "status": "已发货"},
                    platform="taobao"
                )
    """
    
    @abstractmethod
    def get_name(self) -> str:
        """
        平台名称
        
        唯一标识，如 "taobao"、"jd"、"pinduoduo"
        """
        pass
    
    @abstractmethod
    def query_order(self, order_id: str) -> ExternalInfoResponse:
        """
        查询订单
        
        Args:
            order_id: 订单号
            
        Returns:
            ExternalInfoResponse: 订单信息
        """
        pass
    
    @abstractmethod
    def query_logistics(self, logistics_id: str) -> ExternalInfoResponse:
        """
        查询物流
        
        Args:
            logistics_id: 物流单号
            
        Returns:
            ExternalInfoResponse: 物流信息
        """
        pass
    
    @abstractmethod
    def query_refund(self, refund_id: str) -> ExternalInfoResponse:
        """
        查询退款
        
        Args:
            refund_id: 退款单号
            
        Returns:
            ExternalInfoResponse: 退款信息
        """
        pass
    
    @abstractmethod
    def query_user(self, user_id: str) -> ExternalInfoResponse:
        """
        查询用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            ExternalInfoResponse: 用户信息
        """
        pass
    
    @abstractmethod
    def transfer_to_human(self, session_id: str, reason: str) -> ExternalInfoResponse:
        """
        转人工客服
        
        Args:
            session_id: 会话ID
            reason: 转人工原因
            
        Returns:
            ExternalInfoResponse: 转接结果
        """
        pass


class GetExternalInfoTool(BaseTool):
    """
    获取外部信息工具
    
    统一封装不同平台的外部信息获取能力。
    通过注册平台适配器，支持多平台切换。
    
    工具名称：get_external_info
    
    信息类型：
    - order: 订单查询
    - logistics: 物流查询
    - refund: 退款查询
    - user: 用户信息
    - transfer_human: 转人工
    
    使用示例：
        # 1. 注册平台
        tool = GetExternalInfoTool()
        tool.register_platform(TaobaoAdapter())
        tool.register_platform(JDAdapter())
        
        # 2. 调用（由 Agent/LLM 决定怎么用）
        result = tool.execute(
            info_type="order",
            params={"order_id": "12345"}
        )
        
        # 3. 检查结果
        if result.success:
            print(result.data)
    """
    
    def __init__(self):
        """初始化工具"""
        self._platforms: Dict[str, PlatformAdapter] = {}  # 已注册的平台
        self._default_platform: Optional[str] = None       # 默认平台
    
    @property
    def name(self) -> str:
        """工具名称"""
        return "get_external_info"
    
    @property
    def description(self) -> str:
        """
        工具描述
        
        让 LLM 理解此工具能做什么。
        """
        return "获取外部信息：订单查询、物流查询、退款状态、用户信息、转人工客服"
    
    @property
    def tool_type(self) -> ToolType:
        """工具类型是混合类"""
        return ToolType.MIXED
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        参数定义
        
        LLM 调用时需要知道参数格式。
        """
        return {
            "info_type": {
                "type": "string",
                "enum": [e.value for e in InfoType],
                "description": "信息类型：order/logistics/refund/user/transfer_human"
            },
            "params": {
                "type": "object",
                "description": "查询参数，如 order_id, logistics_id 等"
            },
            "platform": {
                "type": "string",
                "description": "指定平台，不指定则使用默认平台"
            }
        }
    
    def register_platform(self, adapter: PlatformAdapter):
        """
        注册平台适配器
        
        Args:
            adapter: 平台适配器实例
        """
        platform_name = adapter.get_name()
        self._platforms[platform_name] = adapter
        # 第一个注册的设为默认平台
        if self._default_platform is None:
            self._default_platform = platform_name
    
    def unregister_platform(self, platform_name: str):
        """
        注销平台
        
        Args:
            platform_name: 平台名称
        """
        if platform_name in self._platforms:
            del self._platforms[platform_name]
        # 如果删除的是默认平台，切换到下一个
        if self._default_platform == platform_name:
            self._default_platform = next(iter(self._platforms), None)
    
    def list_platforms(self) -> List[str]:
        """列出已注册的平台"""
        return list(self._platforms.keys())
    
    def get_platform(self, platform_name: Optional[str] = None) -> Optional[PlatformAdapter]:
        """
        获取平台适配器
        
        Args:
            platform_name: 平台名称，None 表示获取默认平台
            
        Returns:
            PlatformAdapter 或 None
        """
        if platform_name:
            return self._platforms.get(platform_name)
        if self._default_platform:
            return self._platforms.get(self._default_platform)
        return None
    
    def execute(self, **params) -> ToolResult:
        """
        执行工具
        
        Args:
            info_type: 信息类型 (order/logistics/refund/user/transfer_human)
            params: 查询参数，如 {"order_id": "12345"}
            platform: 指定平台（可选）
            
        Returns:
            ToolResult: 执行结果
        """
        info_type_str = params.get("info_type", "")
        query_params = params.get("params", {})
        platform_name = params.get("platform")
        
        # 解析信息类型
        try:
            info_type = InfoType(info_type_str)
        except ValueError:
            return ToolResult(
                success=False,
                error=f"未知的信息类型: {info_type_str}"
            )
        
        # 获取平台
        adapter = self.get_platform(platform_name)
        if not adapter:
            available = ", ".join(self.list_platforms()) or "无"
            return ToolResult(
                success=False,
                error=f"没有可用的平台。当前平台: {available}"
            )
        
        # 执行查询
        try:
            response = self._execute_by_type(adapter, info_type, query_params)
            return ToolResult(
                success=response.success,
                data=response.data,
                message=response.message
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"执行失败: {str(e)}"
            )
    
    def _execute_by_type(
        self,
        adapter: PlatformAdapter,
        info_type: InfoType,
        params: Dict[str, Any]
    ) -> ExternalInfoResponse:
        """
        根据信息类型调用对应平台方法
        
        Args:
            adapter: 平台适配器
            info_type: 信息类型
            params: 查询参数
            
        Returns:
            ExternalInfoResponse
        """
        if info_type == InfoType.ORDER:
            order_id = params.get("order_id", "")
            return adapter.query_order(order_id)
        
        elif info_type == InfoType.LOGISTICS:
            logistics_id = params.get("logistics_id", "")
            return adapter.query_logistics(logistics_id)
        
        elif info_type == InfoType.REFUND:
            refund_id = params.get("refund_id", "")
            return adapter.query_refund(refund_id)
        
        elif info_type == InfoType.USER:
            user_id = params.get("user_id", "")
            return adapter.query_user(user_id)
        
        elif info_type == InfoType.TRANSFER_HUMAN:
            session_id = params.get("session_id", "")
            reason = params.get("reason", "")
            return adapter.transfer_to_human(session_id, reason)
        
        else:
            return ExternalInfoResponse(
                success=False,
                message=f"不支持的类型: {info_type}"
            )


# ============ 全局单例和便捷函数 ============

_tool_instance: Optional[GetExternalInfoTool] = None


def get_external_info_tool() -> GetExternalInfoTool:
    """
    获取全局外部信息工具实例
    
    Returns:
        GetExternalInfoTool 单例
    """
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = GetExternalInfoTool()
    return _tool_instance


def register_platform(adapter: PlatformAdapter):
    """
    注册平台（便捷函数）
    
    快捷方式，无需先获取工具实例。
    
    Args:
        adapter: 平台适配器
    """
    get_external_info_tool().register_platform(adapter)
