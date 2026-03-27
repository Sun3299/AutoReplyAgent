"""
降级策略模块

定义fallback机制，当主要功能失败时提供兜底方案。
"""

from dataclasses import dataclass
from typing import Callable, Any, Optional, List


@dataclass
class FallbackOption:
    """降级选项"""
    name: str                      # 名称
    handler: Callable              # 处理函数
    description: str = ""          # 描述


class FallbackPolicy:
    """
    降级策略
    
    当主要handler失败时，按顺序尝试fallback handlers。
    
    使用示例：
        def primary():
            raise Exception("failed")
        
        def fallback1():
            return "fallback1"
        
        def fallback2():
            return "fallback2"
        
        policy = FallbackPolicy(primary, [
            FallbackOption("opt1", fallback1),
            FallbackOption("opt2", fallback2),
        ])
        
        result = policy.execute()  # 返回 "fallback1"
    """
    
    def __init__(
        self,
        primary: Callable,
        fallbacks: List[FallbackOption] = None,
    ):
        self.primary = primary
        self.fallbacks = fallbacks or []
    
    def execute(self, *args, **kwargs) -> Any:
        """执行主函数，失败时降级"""
        try:
            return self.primary(*args, **kwargs)
        except Exception as e:
            # 尝试降级
            for option in self.fallbacks:
                try:
                    return option.handler(*args, **kwargs)
                except Exception:
                    continue
            
            # 所有降级都失败，抛出原异常
            raise e


class FallbackHandler:
    """
    降级处理器
    
    管理多个降级策略，提供统一的降级入口。
    
    使用示例：
        handler = FallbackHandler()
        
        # 注册降级策略
        handler.register("api", api_fallback_policy)
        handler.register("llm", llm_fallback_policy)
        
        # 执行
        result = handler.execute("api", arg1, arg2)
    """
    
    def __init__(self):
        self._policies = {}
    
    def register(self, name: str, policy: FallbackPolicy):
        """注册降级策略"""
        self._policies[name] = policy
    
    def unregister(self, name: str):
        """注销降级策略"""
        if name in self._policies:
            del self._policies[name]
    
    def get(self, name: str) -> Optional[FallbackPolicy]:
        """获取降级策略"""
        return self._policies.get(name)
    
    def execute(self, name: str, *args, **kwargs) -> Any:
        """执行带降级的函数"""
        policy = self._policies.get(name)
        if not policy:
            raise ValueError(f"No fallback policy: {name}")
        
        return policy.execute(*args, **kwargs)
    
    def list_policies(self) -> List[str]:
        """列出所有降级策略"""
        return list(self._policies.keys())
