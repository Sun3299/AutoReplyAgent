"""
LLM 调用层模块

统一封装不同 LLM Provider 的调用接口。

支持：
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- MiniMax
- 本地模型

设计思想：
- 统一接口：不同 Provider 用同一套 API
- 可插拔：新增 Provider 只需实现 BaseProvider
- 流式支持：支持同步和流式调用
"""

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    Message,
    MessageRole,
)
from .factory import LLMFactory, get_llm
from .fallback import ModelFallbackChain

# Import providers from original providers.py module
from .providers import MiniMaxProvider, MockLLMProvider

# Import new providers
from .claude import ClaudeProvider
from .gpt35 import GPT35Provider

__all__ = [
    # Base classes
    "BaseLLMProvider",
    "LLMResponse",
    "LLMConfig",
    "Message",
    "MessageRole",
    # Factory
    "LLMFactory",
    "get_llm",
    # Fallback
    "ModelFallbackChain",
    # Providers
    "MiniMaxProvider",
    "MockLLMProvider",
    "ClaudeProvider",
    "GPT35Provider",
]
