"""
LLM Provider 工厂

根据配置创建对应的 LLM Provider。
"""

from typing import Dict, Type, Optional

from .base import BaseLLMProvider, LLMConfig


class LLMFactory:
    """
    LLM Provider 工厂
    
    根据模型名称或其他标识创建对应的 Provider 实例。
    
    使用示例：
        factory = LLMFactory()
        factory.register("gpt-4", OpenAIProvider)
        factory.register("claude", AnthropicProvider)
        
        llm = factory.create("gpt-4", api_key="xxx")
    """
    
    def __init__(self):
        """初始化工厂"""
        self._providers: Dict[str, Type[BaseLLMProvider]] = {}
    
    def register(self, name: str, provider_class: Type[BaseLLMProvider]):
        """
        注册 Provider
        
        Args:
            name: Provider 名称/别名
            provider_class: Provider 类
        """
        self._providers[name] = provider_class
    
    def create(self, name: str, **kwargs) -> BaseLLMProvider:
        """
        创建 Provider 实例
        
        Args:
            name: Provider 名称
            **kwargs: 传递给 Provider 的参数（如 api_key）
            
        Returns:
            Provider 实例
            
        Raises:
            ValueError: Provider 未注册
        """
        provider_class = self._providers.get(name)
        if not provider_class:
            available = ", ".join(self._providers.keys())
            raise ValueError(
                f"未注册的 Provider: {name}。"
                f"可用: {available or '无'}"
            )
        
        return provider_class(**kwargs)
    
    def list_providers(self) -> list:
        """列出已注册的 Provider"""
        return list(self._providers.keys())


# 全局工厂实例
_factory: Optional[LLMFactory] = None


def get_factory() -> LLMFactory:
    """获取全局工厂实例"""
    global _factory
    if _factory is None:
        _factory = LLMFactory()
        _register_default_providers(_factory)
    return _factory


def _register_default_providers(factory: LLMFactory):
    """注册默认的 Provider"""
    # 延迟导入，避免循环依赖
    try:
        from .providers import MiniMaxProvider
        factory.register("minimax", MiniMaxProvider)
        factory.register("MiniMax", MiniMaxProvider)
    except ImportError:
        pass
    
    # 注册 Claude Provider
    try:
        from .claude import ClaudeProvider
        factory.register("claude", ClaudeProvider)
        factory.register("Claude", ClaudeProvider)
    except ImportError:
        pass
    
    # 注册 GPT-3.5 Provider
    try:
        from .gpt35 import GPT35Provider
        factory.register("gpt35", GPT35Provider)
        factory.register("gpt-3.5", GPT35Provider)
        factory.register("GPT35", GPT35Provider)
    except ImportError:
        pass


def get_llm(name: str = "minimax", **kwargs) -> BaseLLMProvider:
    """
    便捷函数：获取 LLM 实例
    
    Args:
        name: Provider 名称
        **kwargs: Provider 配置参数
        
    Returns:
        LLM Provider 实例
    """
    factory = get_factory()
    return factory.create(name, **kwargs)
