"""
LLM 模块 - 核心接口定义

定义 LLM 调用的核心抽象：
1. Message - 消息结构
2. LLMConfig - 配置
3. LLMResponse - 响应
4. BaseLLMProvider - Provider 基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator
from enum import Enum
from datetime import datetime


class MessageRole(Enum):
    """消息角色枚举"""
    SYSTEM = "system"     # 系统消息
    USER = "user"         # 用户消息
    ASSISTANT = "assistant"  # 助手消息
    TOOL = "tool"         # 工具消息


@dataclass
class Message:
    """
    对话消息
    
    Attributes:
        role: 消息角色
        content: 消息内容
        name: 可选，发言人名称
        tool_calls: 可选，工具调用列表
    """
    role: MessageRole                # 角色
    content: str                     # 内容
    name: Optional[str] = None      # 名称
    tool_calls: Optional[List[Dict[str, Any]]] = None  # 工具调用


@dataclass
class LLMConfig:
    """
    LLM 配置
    
    Attributes:
        model: 模型名称
        temperature: 温度参数 (0-1)
        max_tokens: 最大 token 数
        top_p: top_p 参数
        timeout: 超时时间（秒）
        api_key: API 密钥
        base_url: API 地址
    """
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: float = 1.0
    timeout: float = 30.0
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    # 扩展参数
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """
    LLM 响应
    
    Attributes:
        content: 生成的文本内容
        usage: token 使用量
        model: 使用的模型
        finish_reason: 结束原因
        raw_response: 原始响应（Provider 相关）
        metadata: 额外元数据（如 fallback 信息）
        error: 错误信息（如果有）
    """
    content: str                              # 内容
    usage: Dict[str, int] = field(default_factory=dict)  # {"prompt_tokens": 100, "completion_tokens": 50}
    model: str = ""                          # 模型
    finish_reason: str = ""                  # 结束原因
    raw_response: Optional[Any] = None        # 原始响应
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    error: Optional[str] = None              # 错误信息


class BaseLLMProvider(ABC):
    """
    LLM Provider 基类
    
    所有 LLM Provider 必须实现此接口。
    
    实现要求：
    - 实现 chat() 方法处理对话
    - 实现 generate() 方法处理生成
    - 支持流式和非流式
    
    使用示例：
        class OpenAIProvider(BaseLLMProvider):
            def chat(self, messages, config) -> LLMResponse:
                # 调用 OpenAI API
                ...
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass
    
    @property
    def default_config(self) -> LLMConfig:
        """默认配置"""
        return LLMConfig()
    
    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        对话补全
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Returns:
            LLMResponse
        """
        pass
    
    @abstractmethod
    async def achat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        异步对话补全
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Returns:
            LLMResponse
        """
        pass
    
    @abstractmethod
    def chat_stream(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """
        流式对话补全
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Yields:
            str: 生成的文本片段
        """
        pass
    
    def generate(
        self,
        prompt: str,
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        简单生成（同步）
        
        将 prompt 包装成单条用户消息调用 chat()。
        """
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return self.chat(messages, config)
    
    async def agenerate(
        self,
        prompt: str,
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """异步简单生成"""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return await self.achat(messages, config)
    
    def chat_stream(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """同步版本的流式聊天（默认实现：调用异步版本）"""
        import asyncio
        
        async def async_gen():
            async for chunk in self.achat_stream(messages, config):
                yield chunk
        
        # 简化：默认调用 chat
        response = self.chat(messages, config)
        yield response.content
    
    async def achat_stream(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """异步版本的流式聊天（默认实现：调用异步 chat）"""
        response = await self.achat(messages, config)
        yield response.content
