"""
LLM Provider Fallback 链

支持多 Provider 级联调用，按优先级尝试并在失败时自动切换。
"""

import time
from typing import List, Optional, Dict, Any, AsyncIterator

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    Message,
)


class ModelFallbackChain:
    """
    LLM Provider 降级链
    
    按优先级尝试不同的 LLM Provider，失败时自动切换到下一个。
    
    特性：
    - 支持指数退避重试（1s, 2s, 4s）
    - 每个模型最多 3 次重试
    - 最多 9 次总尝试（3 模型 × 3 重试）
    - 追踪哪个模型成功响应
    
    使用示例：
        chain = ModelFallbackChain([
            MiniMaxProvider(api_key="xxx"),
            ClaudeProvider(api_key="yyy"),
            GPT35Provider(api_key="zzz"),
        ])
        response = chain.chat(messages)
    """
    
    def __init__(
        self,
        providers: List[BaseLLMProvider],
        base_delay: float = 1.0,
        max_attempts_per_model: int = 3,
    ):
        """
        初始化 Fallback 链
        
        Args:
            providers: Provider 列表，按优先级排序
            base_delay: 指数退避基础延迟（秒）
            max_attempts_per_model: 每个模型最大尝试次数
        """
        self.providers = providers
        self.base_delay = base_delay
        self.max_attempts_per_model = max_attempts_per_model
    
    def chat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None,
    ) -> LLMResponse:
        """
        对话补全（同步）
        
        按优先级尝试每个 Provider，失败时自动切换。
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Returns:
            LLMResponse: 第一个成功的响应
        """
        total_attempts = 0
        max_total_attempts = len(self.providers) * self.max_attempts_per_model
        
        # 记录尝试历史
        attempt_history: List[Dict[str, Any]] = []
        
        for provider in self.providers:
            for attempt in range(self.max_attempts_per_model):
                total_attempts += 1
                
                if total_attempts > max_total_attempts:
                    # 达到最大尝试次数
                    return LLMResponse(
                        content="",
                        error="所有 LLM Provider 均失败",
                        metadata={
                            "success": False,
                            "attempt_history": attempt_history,
                        },
                    )
                
                try:
                    response = provider.chat(messages, config)
                    
                    # 检查是否成功（无错误）
                    if hasattr(response, 'error') and response.error:
                        attempt_history.append({
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "error": response.error,
                        })
                        # 指数退避
                        delay = self.base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    
                    # 成功，记录到 metadata 并返回
                    response.metadata = {
                        "success": True,
                        "model_used": provider.name,
                        "attempt_number": attempt + 1,
                        "total_attempts": total_attempts,
                        "attempt_history": attempt_history,
                    }
                    return response
                    
                except Exception as e:
                    attempt_history.append({
                        "provider": provider.name,
                        "attempt": attempt + 1,
                        "error": str(e),
                    })
                    # 指数退避
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
        
        # 所有 Provider 都失败
        return LLMResponse(
            content="",
            error="所有 LLM Provider 均失败",
            metadata={
                "success": False,
                "attempt_history": attempt_history,
            },
        )
    
    async def achat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None,
    ) -> LLMResponse:
        """
        异步对话补全
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Returns:
            LLMResponse: 第一个成功的响应
        """
        import asyncio
        
        total_attempts = 0
        max_total_attempts = len(self.providers) * self.max_attempts_per_model
        
        attempt_history: List[Dict[str, Any]] = []
        
        for provider in self.providers:
            for attempt in range(self.max_attempts_per_model):
                total_attempts += 1
                
                if total_attempts > max_total_attempts:
                    return LLMResponse(
                        content="",
                        error="所有 LLM Provider 均失败",
                        metadata={
                            "success": False,
                            "attempt_history": attempt_history,
                        },
                    )
                
                try:
                    response = await provider.achat(messages, config)
                    
                    if hasattr(response, 'error') and response.error:
                        attempt_history.append({
                            "provider": provider.name,
                            "attempt": attempt + 1,
                            "error": response.error,
                        })
                        delay = self.base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                    
                    response.metadata = {
                        "success": True,
                        "model_used": provider.name,
                        "attempt_number": attempt + 1,
                        "total_attempts": total_attempts,
                        "attempt_history": attempt_history,
                    }
                    return response
                    
                except Exception as e:
                    attempt_history.append({
                        "provider": provider.name,
                        "attempt": attempt + 1,
                        "error": str(e),
                    })
                    delay = self.base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
        
        return LLMResponse(
            content="",
            error="所有 LLM Provider 均失败",
            metadata={
                "success": False,
                "attempt_history": attempt_history,
            },
        )
    
    def chat_stream(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None,
    ) -> AsyncIterator[str]:
        """
        流式对话补全
        
        注意：流式不支持自动切换，只使用第一个可用 Provider。
        如果需要完整流式降级，需要特殊处理。
        """
        # 流式不支持无缝切换，使用第一个可用 Provider
        provider = self.providers[0]
        yield from provider.chat_stream(messages, config)