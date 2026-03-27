"""
工具注册表

提供工具的注册、配置、动态开关功能。
"""

from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import json

from tools.rag_tool import RagTool as RealRagTool


class ToolType(Enum):
    """工具类型"""
    RAG = "rag"
    EXTERNAL = "external"
    INTERNAL = "internal"


@dataclass
class ToolConfig:
    """工具配置"""
    name: str
    enabled: bool = True
    parallel: bool = True  # 是否支持并行
    timeout: int = 10  # 超时秒数
    retry: int = 3  # 重试次数
    description: str = ""


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: str = ""
    source: str = ""


class BaseTool:
    """工具基类"""
    
    def __init__(self, name: str, tool_type: ToolType):
        self.name = name
        self.tool_type = tool_type
    
    def execute(self, query: str, **kwargs) -> ToolResult:
        """执行工具，返回ToolResult"""
        raise NotImplementedError
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(name=self.name)


class RagTool(BaseTool):
    """RAG查询工具（壳子）"""
    
    def __init__(self):
        super().__init__("rag", ToolType.RAG)
    
    def execute(self, query: str, **kwargs) -> ToolResult:
        """RAG查询
        
        Args:
            query: 查询内容
            top_k: 返回数量
            
        Returns:
            ToolResult
        """
        # TODO: 用户实现具体RAG查询逻辑
        # 示例：
        # from rag import retrieve
        # results = retrieve(query, top_k=kwargs.get("top_k", 3))
        # return ToolResult(success=True, data=results, source="rag")
        
        return ToolResult(
            success=True,
            data=[f"[RAG查询占位] query={query}"],
            source="rag"
        )
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name=self.name,
            enabled=True,
            parallel=True,
            timeout=10,
            retry=3,
            description="RAG知识库查询"
        )


class ExternalTool(BaseTool):
    """外部知识查询工具（壳子）"""
    
    def __init__(self):
        super().__init__("external", ToolType.EXTERNAL)
    
    def execute(self, query: str, **kwargs) -> ToolResult:
        """外部知识查询
        
        Args:
            query: 查询内容
            info_type: 查询类型 (order/logistics/refund/user)
            
        Returns:
            ToolResult
        """
        # TODO: 用户实现具体外部查询逻辑
        # 示例：
        # from tools import get_external_info_tool
        # tool = get_external_info_tool()
        # result = tool.execute(
        #     info_type=kwargs.get("info_type", "order"),
        #     params={"query": query}
        # )
        # return ToolResult(success=result.success, data=result.data, source="external")
        
        info_type = kwargs.get("info_type", "order")
        return ToolResult(
            success=True,
            data=[f"[外部查询占位] query={query}, type={info_type}"],
            source="external"
        )
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name=self.name,
            enabled=True,
            parallel=True,
            timeout=15,
            retry=2,
            description="外部业务系统查询（订单/物流/退款/用户）"
        )


class ToolRegistry:
    """
    工具注册表
    
    管理所有工具的注册、配置、查询。
    
    使用示例：
        registry = ToolRegistry()
        registry.register(RagTool())
        registry.register(ExternalTool())
        
        # 获取可并行的工具
        parallel_tools = registry.list_parallel()
        
        # 执行工具
        result = registry.execute("rag", "退货政策")
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._configs: Dict[str, ToolConfig] = {}
    
    def register(self, tool: BaseTool, config: ToolConfig = None):
        """注册工具"""
        self._tools[tool.name] = tool
        self._configs[tool.name] = config or tool.get_config()
    
    def unregister(self, name: str):
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
        if name in self._configs:
            del self._configs[name]
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def get_config(self, name: str) -> Optional[ToolConfig]:
        """获取工具配置"""
        return self._configs.get(name)
    
    def list_all(self) -> List[str]:
        """列出所有工具名"""
        return list(self._tools.keys())
    
    def list_enabled(self) -> List[str]:
        """列出已启用的工具"""
        return [
            name for name, cfg in self._configs.items()
            if cfg.enabled
        ]
    
    def list_parallel(self) -> List[str]:
        """列出支持并行的工具"""
        return [
            name for name, cfg in self._configs.items()
            if cfg.enabled and cfg.parallel
        ]
    
    def execute(self, name: str, query: str, **kwargs) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"工具不存在: {name}")
        
        config = self.get_config(name)
        if not config.enabled:
            return ToolResult(success=False, error=f"工具已禁用: {name}")
        
        try:
            return tool.execute(query, **kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e), source=name)
    
    def update_config(self, name: str, **kwargs):
        """更新工具配置"""
        if name in self._configs:
            cfg = self._configs[name]
            for key, value in kwargs.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
    
    def load_from_json(self, path: str):
        """从JSON加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            configs = json.load(f)
        for name, cfg in configs.items():
            self.update_config(name, **cfg)
    
    def save_to_json(self, path: str):
        """保存配置到JSON"""
        configs = {
            name: {
                "enabled": cfg.enabled,
                "parallel": cfg.parallel,
                "timeout": cfg.timeout,
                "retry": cfg.retry
            }
            for name, cfg in self._configs.items()
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(configs, f, ensure_ascii=False, indent=2)


# 全局注册表
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # 注册默认工具
        _registry.register(RealRagTool())
        _registry.register(ExternalTool())
    return _registry


def register_tool(tool: BaseTool):
    """注册工具（便捷函数）"""
    get_registry().register(tool)


def execute_tool(name: str, query: str, **kwargs) -> ToolResult:
    """执行工具（便捷函数）"""
    return get_registry().execute(name, query, **kwargs)
