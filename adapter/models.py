from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid


class Channel(str, Enum):
    WEB = "web"
    WXMP = "wxmp"
    MINIPROGRAM = "miniprogram"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    QQ = "qq"
    OTHER = "other"


class MsgType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"
    CARD = "card"
    EVENT = "event"


@dataclass
class MediaInfo:
    url: Optional[str] = None
    format: Optional[str] = None
    duration: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.url:
            result["url"] = self.url
        if self.format:
            result["format"] = self.format
        if self.duration:
            result["duration"] = self.duration
        return result


@dataclass
class SenderInfo:
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.nickname:
            result["nickname"] = self.nickname
        if self.avatar:
            result["avatar"] = self.avatar
        if self.phone:
            result["phone"] = self.phone
        return result


@dataclass
class Extension:
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"customData": self.custom_data}
        if self.order_id:
            result["orderId"] = self.order_id
        if self.product_id:
            result["productId"] = self.product_id
        return result


@dataclass
class UserMessage:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    channel: str = Channel.OTHER
    session_id: str = ""
    msg_type: str = MsgType.TEXT
    content: str = ""
    media: Optional[MediaInfo] = None
    sender_info: Optional[SenderInfo] = None
    extension: Extension = field(default_factory=Extension)
    create_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "requestId": self.request_id,
            "userId": self.user_id,
            "channel": self.channel,
            "sessionId": self.session_id,
            "msgType": self.msg_type,
            "content": self.content,
            "createTime": self.create_time,
        }
        if self.media:
            result["media"] = self.media.to_dict()
        if self.sender_info:
            result["senderInfo"] = self.sender_info.to_dict()
        result["extension"] = self.extension.to_dict()
        return result
