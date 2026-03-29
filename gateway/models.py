"""
Gateway 数据模型

InboundRequest, OutboundResponse, Message, ContentBlock 等核心数据结构。

统一消息格式：
- Message.content 是一个 ContentBlock 列表
- ContentBlock 通过 type 字段区分不同类型
- 每种 type 有不同的结构
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Union
from enum import Enum


class ContentBlockType(Enum):
    """ContentBlock 类型枚举"""

    TEXT = "text"  # 普通文本
    HISTORY = "history"  # 历史消息
    CURRENT = "current"  # 当前消息
    RAG = "rag"  # RAG 检索结果
    TOOL_RESULT = "tool_result"  # 工具执行结果
    TOOL_USE = "tool_use"  # 工具调用请求


@dataclass
class ContentBlock:
    """
    内容块

    通过 type 字段区分不同类型，每种类型有不同结构：
    - text: 普通文本内容
    - history: 历史对话消息 (带 round, timestamp)
    - current: 当前用户消息 (带 round)
    - rag: RAG 检索结果 (带 source)
    - tool_result: 工具执行结果 (带 tool_name, success)
    - tool_use: 工具调用请求 (带 tool_name, tool_input)
    """

    type: str  # ContentBlockType 的值
    text: str = ""  # text/history/current/rag 类型的内容
    round: int = 0  # 对话轮次 (history/current)
    timestamp: str = ""  # 时间戳 (history)
    source: str = ""  # 来源: user/llm/system (history)
    tool_name: str = ""  # 工具名称 (tool_result/tool_use)
    tool_use_id: str = ""  # 工具调用 ID (tool_result 关联 tool_use)
    success: bool = True  # 是否成功 (tool_result)
    tool_input: Optional[Dict[str, Any]] = None  # 工具输入参数 (tool_use)

    def to_dict(self) -> dict:
        """转换为字典"""
        result: Dict[str, Any] = {"type": self.type}
        if self.text:
            result["text"] = self.text
        if self.round:
            result["round"] = self.round
        if self.timestamp:
            result["timestamp"] = self.timestamp
        if self.source:
            result["source"] = self.source
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_use_id:
            result["tool_use_id"] = self.tool_use_id
        if not self.success:
            result["success"] = self.success
        if self.tool_input:
            result["tool_input"] = self.tool_input
        return result

    @classmethod
    def text_block(cls, text: str) -> "ContentBlock":
        """创建文本块"""
        return cls(type=ContentBlockType.TEXT.value, text=text)

    @classmethod
    def history_block(
        cls, text: str, round: int, timestamp: str = "", source: str = ""
    ) -> "ContentBlock":
        """创建历史消息块"""
        return cls(
            type=ContentBlockType.HISTORY.value,
            text=text,
            round=round,
            timestamp=timestamp,
            source=source,
        )

    @classmethod
    def current_block(cls, text: str, round: int = 0) -> "ContentBlock":
        """创建当前消息块"""
        return cls(type=ContentBlockType.CURRENT.value, text=text, round=round)

    @classmethod
    def rag_block(cls, text: str, source: str = "knowledge_base") -> "ContentBlock":
        """创建 RAG 结果块"""
        return cls(type=ContentBlockType.RAG.value, text=text, source=source)

    @classmethod
    def tool_result_block(
        cls, text: str, tool_name: str, tool_use_id: str = "", success: bool = True
    ) -> "ContentBlock":
        """创建工具结果块"""
        return cls(
            type=ContentBlockType.TOOL_RESULT.value,
            text=text,
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            success=success,
        )

    @classmethod
    def tool_use_block(
        cls, tool_name: str, tool_input: Dict[str, Any], tool_use_id: str = ""
    ) -> "ContentBlock":
        """创建工具调用块"""
        return cls(
            type=ContentBlockType.TOOL_USE.value,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
        )


@dataclass
class Message:
    """
    统一消息结构

    消息内容通过 content_blocks 列表传递，每项是 ContentBlock 类型。

    Attributes:
        role: 消息角色 (system/user/assistant)
        content_blocks: 内容块列表，按类型区分不同内容
    """

    role: str
    content_blocks: List[ContentBlock] = field(default_factory=list)
    name: Optional[str] = None  # 发言人名称

    def to_dict(self) -> dict:
        """转换为 LLM API 格式"""
        content = []
        for block in self.content_blocks:
            content.append(block.to_dict())

        result: Dict[str, Any] = {"role": self.role, "content": content}
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def system_message(cls, text: str) -> "Message":
        """创建系统消息"""
        return cls(role="system", content_blocks=[ContentBlock.text_block(text)])

    @classmethod
    def user_message(cls, blocks: List[ContentBlock]) -> "Message":
        """创建用户消息"""
        return cls(role="user", content_blocks=blocks)

    @classmethod
    def assistant_message(cls, text: str) -> "Message":
        """创建助手消息"""
        return cls(role="assistant", content_blocks=[ContentBlock.text_block(text)])


@dataclass
class Media:
    """媒体信息"""

    url: Optional[str] = None
    format: Optional[str] = None
    duration: Optional[str] = None


@dataclass
class SenderInfo:
    """发送者信息"""

    nickname: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None


@dataclass
class InboundRequest:
    """入站请求"""

    requestId: str
    userId: str
    channel: str
    sessionId: str
    msgType: str
    content: str
    media: Optional[Media] = None
    senderInfo: Optional[SenderInfo] = None
    extension: Dict[str, Any] = field(default_factory=dict)
    createTime: str = ""

    @property
    def session_key(self) -> str:
        """会话主键: sessionId:userId:channel"""
        return f"{self.sessionId}:{self.userId}:{self.channel}"


# 向后兼容别名
ChatRequest = InboundRequest


@dataclass
class OutboundResponse:
    """出站响应"""

    requestId: str
    responseId: str
    sessionId: str
    content: str
    media: Optional[Media] = None
    traceId: str = ""
    sources: List[Any] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# 向后兼容别名
ChatResponse = OutboundResponse
