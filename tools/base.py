"""
Tools 模块 - 基础类定义

本模块定义了工具系统的核心抽象：

1. ToolType - 工具类型枚举
2. ToolResult - 工具执行结果
3. ToolCall - 工具调用记录
4. BaseTool - 所有工具的基类
5. MockTool - 用于测试的 Mock 工具

设计原则：
- 统一接口：所有工具继承 BaseTool
- 结果标准化：执行结果统一用 ToolResult
- 可测试性：提供 MockTool 方便单元测试
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum
from datetime import datetime


class ToolType(Enum):
    """
    工具类型枚举
    
    用于区分工具的能力类型：
    - QUERY: 查询类工具，只读操作
    - ACTION: 操作类工具，会修改数据
    - MIXED: 混合类，既有查询又有操作
    """
    QUERY = "query"     # 查询类（只读）
    ACTION = "action"   # 操作类（会修改）
    MIXED = "mixed"     # 混合类


@dataclass
class ToolResult:
    """
    工具执行结果
    
    所有工具执行后都返回此结构，保证调用方有一致的接口。
    
    Attributes:
        success: 执行是否成功
        data: 返回的数据（查询结果等）
        message: 提示信息（如"查询成功"）
        error: 错误信息（失败时填充）
    
    使用示例：
        result = tool.execute(order_id="12345")
        if result.success:
            print(result.data)
        else:
            print(result.error)
    """
    success: bool                        # 是否成功
    data: Optional[Any] = None          # 返回数据
    message: str = ""                   # 提示信息
    error: Optional[str] = None          # 错误信息
    
    def to_dict(self) -> dict:
        """转换为字典格式，便于 JSON 序列化"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error
        }


@dataclass
class ToolCall:
    """
    工具调用记录
    
    记录一次工具调用的完整信息，用于：
    - 追踪执行历史
    - 调试问题
    - 生成执行日志
    
    Attributes:
        tool_name: 工具名称
        params: 调用参数
        result: 执行结果
        duration: 执行耗时（秒）
        timestamp: 调用时间
    """
    tool_name: str                                      # 工具名称
    params: Dict[str, Any] = field(default_factory=dict)  # 调用参数
    result: Optional[ToolResult] = None                # 执行结果
    duration: float = 0.0                               # 耗时（秒）
    timestamp: datetime = field(default_factory=datetime.now)  # 调用时间


class BaseTool(ABC):
    """
    工具基类
    
    所有具体工具必须继承此类并实现抽象方法。
    
    设计模式：模板方法模式
    - execute() 是模板方法，定义了执行流程
    - 子类实现具体的业务逻辑
    
    属性说明：
    - name: 工具的唯一标识，Agent 通过此名称调用
    - description: 工具描述，让 LLM 理解工具用途
    - tool_type: 工具类型，影响 Agent 的调用策略
    - parameters: 参数定义，JSON Schema 格式
    
    使用示例：
        class OrderTool(BaseTool):
            @property
            def name(self) -> str:
                return "order_tool"
            
            @property
            def description(self) -> str:
                return "查询订单状态和详情"
            
            def execute(self, **params) -> ToolResult:
                order_id = params.get("order_id")
                # 查询逻辑
                return ToolResult(success=True, data={...})
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        工具名称
        
        唯一标识，Agent 调用时使用。
        建议使用 snake_case 格式，如 "order_tool"
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        工具描述
        
        用于 LLM 理解工具能做什么。
        建议包含：功能说明、返回内容、使用场景。
        """
        pass
    
    @property
    def tool_type(self) -> ToolType:
        """
        工具类型
        
        默认是查询类。
        - QUERY: 只读操作，如查询订单
        - ACTION: 写操作，如退款
        - MIXED: 混合
        """
        return ToolType.QUERY
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        参数定义
        
        JSON Schema 格式，用于：
        - LLM 理解需要什么参数
        - 参数校验
        
        返回格式示例：
        {
            "order_id": {
                "type": "string",
                "description": "订单号"
            }
        }
        """
        return {}
    
    @abstractmethod
    def execute(self, **params) -> ToolResult:
        """
        执行工具
        
        模板方法，定义了执行流程：
        1. 参数校验
        2. 调用具体业务逻辑
        3. 返回结果
        
        Args:
            **params: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    def validate_params(self, **params) -> tuple:
        """
        验证参数
        
        子类可覆盖此方法实现参数校验。
        
        Args:
            **params: 待验证的参数
            
        Returns:
            (is_valid, error_message)
            - is_valid: 参数是否有效
            - error_message: 错误信息（无效时返回）
        """
        return True, ""
    
    def get_schema(self) -> dict:
        """
        获取工具的完整 Schema
        
        用于 Agent 工具注册和 LLM 理解工具。
        
        Returns:
            包含 name、description、type、parameters 的字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "type": self.tool_type.value,
            "parameters": self.parameters
        }


class MockTool(BaseTool):
    """
    Mock 工具 - 用于测试
    
    简单实现，返回预设的结果，不做实际操作。
    用于在没有真实后端时测试工具调用流程。
    
    使用示例：
        tool = MockTool(name="test_tool", description="测试工具")
        result = tool.execute(param1="value")
    """
    
    def __init__(self, name: str = "mock_tool", description: str = "Mock工具"):
        """
        初始化 Mock 工具
        
        Args:
            name: 工具名称
            description: 工具描述
        """
        self._name = name
        self._description = description
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    def execute(self, **params) -> ToolResult:
        """
        执行 Mock 工具
        
        简单地返回成功结果，包含传入的参数。
        """
        return ToolResult(
            success=True,
            data=params,
            message=f"Mock tool executed: {self._name}"
        )
