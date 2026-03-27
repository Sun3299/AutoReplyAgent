"""
重试策略模块

实现指数退避重试机制。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Any, Optional
import time
import random


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3          # 最大尝试次数
    base_delay: float = 1.0       # 基础延迟（秒）
    max_delay: float = 30.0        # 最大延迟（秒）
    exponential_base: float = 2.0    # 指数基数
    jitter: bool = True            # 是否添加抖动


class ExponentialBackoff:
    """
    指数退避重试策略
    
    计算公式：
    delay = min(base_delay * (exponential_base ^ attempt), max_delay)
    + random jitter
    
    Attributes:
        config: 重试配置
    """
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        return attempt < self.config.max_attempts
    
    def get_delay(self, attempt: int) -> float:
        """获取下次重试延迟"""
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )
        
        if self.config.jitter:
            delay *= (0.5 + random.random())  # 0.5 ~ 1.5
        
        return delay
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行带重试的函数
        
        Args:
            func: 要执行的函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            最后一次执行的异常
        """
        last_error = None
        
        for attempt in range(self.config.max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                if not self.should_retry(attempt, e):
                    raise last_error
                
                delay = self.get_delay(attempt)
                time.sleep(delay)
        
        raise last_error


class RetryContext:
    """重试上下文"""
    
    def __init__(
        self,
        attempt: int,
        max_attempts: int,
        delay: float,
        error: Exception,
    ):
        self.attempt = attempt
        self.max_attempts = max_attempts
        self.delay = delay
        self.error = error
    
    @property
    def will_retry(self) -> bool:
        return self.attempt < self.max_attempts


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True,
):
    """
    重试装饰器
    
    使用示例：
        @retry(max_attempts=3, base_delay=1.0)
        def call_api():
            return requests.get("https://api.example.com/data")
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            policy = ExponentialBackoff(RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                exponential_base=exponential_base,
                max_delay=max_delay,
                jitter=jitter,
            ))
            return policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator
