"""
平台工具基类

各平台工具继承此基类。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: str = ""
    message: str = ""


class BaseChannelTool(ABC):
    """平台工具基类"""
    
    def __init__(self, channel: str):
        self.channel = channel
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @abstractmethod
    def execute(self, **params) -> ToolResult:
        """执行工具"""
        pass
    
    def validate_params(self, **params) -> tuple:
        """验证参数，默认返回成功"""
        return True, ""


class MockOrderTool(BaseChannelTool):
    """模拟订单查询工具（用于演示）"""
    
    @property
    def name(self) -> str:
        return f"{self.channel}_order"
    
    @property
    def description(self) -> str:
        return f"{self.channel}订单查询工具"
    
    def execute(self, **params) -> ToolResult:
        order_id = params.get("order_id", "N/A")
        user_id = params.get("user_id", "N/A")
        
        return ToolResult(
            success=True,
            data={
                "order_id": order_id,
                "user_id": user_id,
                "status": "已发货",
                "channel": self.channel,
                "note": f"这是 {self.channel} 平台的模拟订单数据"
            },
            message="订单查询成功"
        )


class MockLogisticsTool(BaseChannelTool):
    """模拟物流查询工具（用于演示）"""
    
    @property
    def name(self) -> str:
        return f"{self.channel}_logistics"
    
    @property
    def description(self) -> str:
        return f"{self.channel}物流查询工具"
    
    def execute(self, **params) -> ToolResult:
        logistics_id = params.get("logistics_id", "N/A")
        
        return ToolResult(
            success=True,
            data={
                "logistics_id": logistics_id,
                "status": "运输中",
                "location": "上海分拨中心",
                "channel": self.channel,
                "note": f"这是 {self.channel} 平台的模拟物流数据"
            },
            message="物流查询成功"
        )
