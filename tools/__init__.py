"""
Tools 工具层

设计思想：
- 原子化：每个工具职责单一，可独立使用
- 动态编排：由 LLM 根据场景自由组合工具
- 可插拔：工具可注册、注销、配置

工具清单：
1. RagTool - RAG知识库查询
2. ExternalTool - 外部业务查询（订单/物流/退款/用户）

使用示例：
    from tools import get_registry, register_tool
    
    registry = get_registry()
    
    # 执行RAG查询
    result = registry.execute("rag", "退货政策")
    
    # 执行外部查询
    result = registry.execute("external", "查订单", info_type="order")
"""

from .base import BaseTool, ToolResult, ToolCall, ToolType
from .rag_tool import RagTool
from .registry import (
    ToolRegistry,
    ToolConfig,
    ExternalTool,
    get_registry,
    register_tool,
    execute_tool,
)

__all__ = [
    # 基础类
    "BaseTool",
    "ToolResult",
    "ToolCall",
    "ToolType",
    "ToolConfig",
    
    # 注册器
    "ToolRegistry",
    "get_registry",
    "register_tool",
    "execute_tool",
    
    # 工具
    "RagTool",
    "ExternalTool",
]
