"""
平台工具注册表

根据 channel 注册和管理平台专属工具。
"""

from typing import Dict, List, Optional, Any

from tools.channels.base import BaseChannelTool, MockOrderTool, MockLogisticsTool, ToolResult


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        # 全局工具注册表: channel -> {tool_name: tool_instance}
        self._registry: Dict[str, Dict[str, BaseChannelTool]] = {}
        
        # 默认工具（所有平台都有的）
        self._default_tools: Dict[str, str] = {
            "rag": "RAG知识库检索",
        }
    
    def register_tool(self, channel: str, tool: BaseChannelTool):
        """注册一个工具"""
        if channel not in self._registry:
            self._registry[channel] = {}
        self._registry[channel][tool.name] = tool
    
    def get_tool(self, channel: str, tool_name: str) -> Optional[BaseChannelTool]:
        """获取指定 channel 的工具"""
        if channel not in self._registry:
            return None
        return self._registry[channel].get(tool_name)
    
    def get_tools(self, channel: str) -> Dict[str, BaseChannelTool]:
        """获取指定 channel 的所有工具"""
        return self._registry.get(channel, {})
    
    def get_tool_names(self, channel: str) -> List[str]:
        """获取指定 channel 的所有工具名称"""
        return list(self.get_tools(channel).keys())
    
    def has_tool(self, channel: str, tool_name: str) -> bool:
        """检查指定 channel 是否有某个工具"""
        return self.get_tool(channel, tool_name) is not None


# 全局工具注册表
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _init_default_tools(_registry)
    return _registry


def _init_default_tools(registry: ToolRegistry):
    """初始化各平台的默认工具"""
    
    # xianyu 平台工具
    from tools.channels.xianyu_tools import get_xianyu_tools
    for name, tool in get_xianyu_tools().items():
        registry.register_tool("xianyu", tool)
    
    # web 平台工具
    registry.register_tool("web", MockOrderTool("web"))
    registry.register_tool("web", MockLogisticsTool("web"))
    
    # feishu 平台工具
    registry.register_tool("feishu", MockOrderTool("feishu"))
    
    # 通用工具 - 各平台都需要 RAG，但 RagTool 是特殊处理的在 tools_step 里
    # 所以这里不需要注册


def get_channel_tools(channel: str) -> Dict[str, BaseChannelTool]:
    """获取指定 channel 的所有工具"""
    return get_tool_registry().get_tools(channel)


def get_tool(channel: str, tool_name: str) -> Optional[BaseChannelTool]:
    """获取指定 channel 的指定工具"""
    return get_tool_registry().get_tool(channel, tool_name)
