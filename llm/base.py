"""
LLM 模块 - 核心接口定义

基于 OpenClaw 结构设计：
1. ContentBlock - 内容块（TextContent/ThinkingContent/ToolCall/ImageContent）
2. Message - 消息（UserMessage/AssistantMessage/ToolResultMessage）
3. Tool - 工具定义
4. Usage - Token 使用量
5. LLMConfig - 配置
6. LLMResponse - 响应
7. BaseLLMProvider - Provider 基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncIterator
from enum import Enum


# ============================================================
# ContentBlock 类型
# ============================================================


class ContentBlockType(Enum):
    """ContentBlock 类型枚举"""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "toolCall"
    IMAGE = "image"


@dataclass
class TextContent:
    """
    文本内容块

    Attributes:
        type: 固定为 "text"
        text: 文本内容
        text_signature: 签名（可选）
    """

    type: str = "text"
    text: str = ""
    text_signature: Optional[str] = None

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {"type": self.type, "text": self.text}
        if self.text_signature:
            result["textSignature"] = self.text_signature
        return result


@dataclass
class ThinkingContent:
    """
    思考内容块（用于 reasoning models）

    Attributes:
        type: 固定为 "thinking"
        thinking: 思考内容
        thinking_signature: 思考签名（可选）
        redacted: 是否被安全过滤器屏蔽
    """

    type: str = "thinking"
    thinking: str = ""
    thinking_signature: Optional[str] = None
    redacted: bool = False

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {"type": self.type, "thinking": self.thinking}
        if self.thinking_signature:
            result["thinkingSignature"] = self.thinking_signature
        if self.redacted:
            result["redacted"] = self.redacted
        return result


@dataclass
class ToolCall:
    """
    工具调用块

    Attributes:
        type: 固定为 "toolCall"
        id: 工具调用唯一ID
        name: 工具名称
        arguments: 工具参数（对象）
        thought_signature: 思考签名（可选）
    """

    type: str = "toolCall"
    id: str = ""
    name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    thought_signature: Optional[str] = None

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.thought_signature:
            result["thoughtSignature"] = self.thought_signature
        return result


@dataclass
class ImageContent:
    """
    图片内容块

    Attributes:
        type: 固定为 "image"
        data: base64 编码的图片数据
        mime_type: MIME 类型
    """

    type: str = "image"
    data: str = ""  # base64
    mime_type: str = "image/png"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "mimeType": self.mime_type,
        }


# ============================================================
# ContentBlock 联合类型
# ============================================================

ContentBlock = Union[TextContent, ThinkingContent, ToolCall, ImageContent]


# ============================================================
# Message 类型
# ============================================================


class MessageRole(Enum):
    """消息角色枚举"""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "toolResult"
    SYSTEM = "system"


@dataclass
class UserMessage:
    """
    用户消息

    Attributes:
        role: 固定为 "user"
        content: 消息内容（字符串或内容块数组）
        timestamp: Unix 时间戳（毫秒）
    """

    role: str = "user"
    content: Union[str, List[ContentBlock]] = ""
    timestamp: int = 0

    def to_dict(self) -> dict:
        if isinstance(self.content, str):
            return {
                "role": self.role,
                "content": self.content,
                "timestamp": self.timestamp,
            }
        else:
            blocks = []
            for block in self.content:
                if isinstance(block, TextContent):
                    blocks.append(block.to_dict())
                elif isinstance(block, ThinkingContent):
                    blocks.append(block.to_dict())
                elif isinstance(block, ToolCall):
                    blocks.append(block.to_dict())
                elif isinstance(block, ImageContent):
                    blocks.append(block.to_dict())
            return {
                "role": self.role,
                "content": blocks,
                "timestamp": self.timestamp,
            }


@dataclass
class AssistantMessage:
    """
    助手消息

    Attributes:
        role: 固定为 "assistant"
        content: 内容块数组（TextContent | ThinkingContent | ToolCall）
        api: API 类型
        provider: 提供者
        model: 模型名称
        usage: Token 使用量
        stop_reason: 停止原因
        error_message: 错误信息（可选）
        timestamp: Unix 时间戳（毫秒）
    """

    role: str = "assistant"
    content: List[ContentBlock] = field(default_factory=list)
    api: str = ""
    provider: str = ""
    model: str = ""
    usage: Optional["Usage"] = None
    stop_reason: str = "stop"
    error_message: Optional[str] = None
    timestamp: int = 0

    def to_dict(self) -> dict:
        blocks = []
        for block in self.content:
            if isinstance(block, TextContent):
                blocks.append(block.to_dict())
            elif isinstance(block, ThinkingContent):
                blocks.append(block.to_dict())
            elif isinstance(block, ToolCall):
                blocks.append(block.to_dict())
            elif isinstance(block, ImageContent):
                blocks.append(block.to_dict())

        result: Dict[str, Any] = {
            "role": self.role,
            "content": blocks,
            "api": self.api,
            "provider": self.provider,
            "model": self.model,
            "stopReason": self.stop_reason,
            "timestamp": self.timestamp,
        }
        if self.usage:
            result["usage"] = self.usage.to_dict()
        if self.error_message:
            result["errorMessage"] = self.error_message
        return result


@dataclass
class ToolResultMessage:
    """
    工具结果消息

    Attributes:
        role: 固定为 "toolResult"
        tool_call_id: 对应工具调用的ID
        tool_name: 工具名称
        content: 结果内容块数组（TextContent | ImageContent）
        details: 详细结果（可选）
        is_error: 是否错误
        timestamp: Unix 时间戳（毫秒）
    """

    role: str = "toolResult"
    tool_call_id: str = ""
    tool_name: str = ""
    content: List[ContentBlock] = field(default_factory=list)
    details: Optional[Any] = None
    is_error: bool = False
    timestamp: int = 0

    def to_dict(self) -> dict:
        blocks = []
        for block in self.content:
            if isinstance(block, TextContent):
                blocks.append(block.to_dict())
            elif isinstance(block, ImageContent):
                blocks.append(block.to_dict())

        result: Dict[str, Any] = {
            "role": self.role,
            "toolCallId": self.tool_call_id,
            "toolName": self.tool_name,
            "content": blocks,
            "isError": self.is_error,
            "timestamp": self.timestamp,
        }
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class SystemMessage:
    """
    系统消息（简化版，用于构建请求）

    Attributes:
        role: 固定为 "system"
        content: 系统提示内容
    """

    role: str = "system"
    content: str = ""

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
        }


# Message 联合类型
Message = Union[UserMessage, AssistantMessage, ToolResultMessage, SystemMessage]


# ============================================================
# 工具定义
# ============================================================


@dataclass
class Tool:
    """
    工具定义

    Attributes:
        name: 工具名称
        description: 工具描述
        parameters: JSON Schema 格式的参数定义
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ============================================================
# Token 使用量
# ============================================================


@dataclass
class Usage:
    """
    Token 使用量

    Attributes:
        input: 输入 token 数
        output: 输出 token 数
        cache_read: 缓存读取 token 数
        cache_write: 缓存写入 token 数
        total_tokens: 总 token 数
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "output": self.output,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
            "totalTokens": self.total_tokens,
        }


# ============================================================
# LLM 配置
# ============================================================


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
        stream: 是否流式输出
        store: 是否存储
    """

    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: float = 1.0
    timeout: float = 30.0
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    stream: bool = True
    store: bool = False

    # 扩展参数
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# LLM 响应
# ============================================================


@dataclass
class LLMResponse:
    """
    LLM 响应

    Attributes:
        content: 生成的文本内容
        usage: token 使用量
        model: 使用的模型
        finish_reason: 停止原因
        raw_response: 原始响应
        metadata: 额外元数据
        error: 错误信息
    """

    content: str = ""
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""
    raw_response: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ============================================================
# BaseLLMProvider
# ============================================================


class BaseLLMProvider(ABC):
    """
    LLM Provider 基类

    所有 LLM Provider 必须实现此接口。
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
        self, messages: List[Message], config: Optional[LLMConfig] = None
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
        self, messages: List[Message], config: Optional[LLMConfig] = None
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
        self, messages: List[Message], config: Optional[LLMConfig] = None
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

    def generate(self, prompt: str, config: Optional[LLMConfig] = None) -> LLMResponse:
        """简单生成（同步）"""
        messages: List[Message] = [UserMessage(content=prompt)]
        return self.chat(messages, config)

    async def agenerate(
        self, prompt: str, config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """异步简单生成"""
        messages: List[Message] = [UserMessage(content=prompt)]
        return await self.achat(messages, config)

    def chat_stream(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """同步版本的流式聊天"""
        import asyncio

        async def async_gen():
            async for chunk in self.achat_stream(messages, config):
                yield chunk

        response = self.chat(messages, config)
        yield response.content

    async def achat_stream(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """异步版本的流式聊天"""
        response = await self.achat(messages, config)
        yield response.content
