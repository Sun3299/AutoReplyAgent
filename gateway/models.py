"""
Gateway 数据模型

InboundRequest, OutboundResponse 等核心数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


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
