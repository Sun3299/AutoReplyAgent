from typing import Any, Dict, Optional
from adapter.models import UserMessage, MediaInfo, SenderInfo, Extension, Channel, MsgType
import uuid
from datetime import datetime


class MessageAdapter:
    def __init__(self):
        self._channel_converters = {
            "web": self._convert_web,
            "wxmp": self._convert_wxmp,
            "dingtalk": self._convert_dingtalk,
            "feishu": self._convert_feishu,
        }

    def convert(self, channel: str, raw_message: Dict[str, Any]) -> Dict[str, Any]:
        converter = self._channel_converters.get(channel, self._convert_default)
        user_message = converter(raw_message)
        return user_message.to_dict()

    def _safe_get(self, raw: Dict[str, Any], *keys, default="") -> str:
        for key in keys:
            val = raw.get(key, default)
            if val is None:
                return ""
            if isinstance(val, str):
                return val
            return str(val)
        return ""

    def _safe_get_dict(self, raw: Dict[str, Any], key: str, default=None) -> Any:
        val = raw.get(key, default)
        if val is None:
            return default
        return val

    def _create_base_message(self, channel: str) -> UserMessage:
        return UserMessage(
            request_id=str(uuid.uuid4()),
            channel=channel,
            create_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _convert_web(self, raw: Dict[str, Any]) -> UserMessage:
        msg = self._create_base_message(Channel.WEB)
        msg.user_id = self._safe_get(raw, "user_id", "userId")
        msg.session_id = self._safe_get(raw, "session_id", "sessionId")
        msg.msg_type = raw.get("msg_type", raw.get("msgType", MsgType.TEXT))
        msg.content = self._safe_get(raw, "content")
        nickname = self._safe_get(raw, "nickname")
        avatar = self._safe_get(raw, "avatar")
        msg.sender_info = SenderInfo(nickname=nickname or None, avatar=avatar or None)
        return msg

    def _convert_wxmp(self, raw: Dict[str, Any]) -> UserMessage:
        msg = self._create_base_message(Channel.WXMP)
        msg.user_id = self._safe_get(raw, "FromUserName")
        msg.session_id = raw.get("MsgId", str(uuid.uuid4()))
        msg_type_map = {
            "text": MsgType.TEXT,
            "image": MsgType.IMAGE,
            "voice": MsgType.VOICE,
            "video": MsgType.VIDEO,
        }
        msg.msg_type = msg_type_map.get(raw.get("MsgType", "text"), MsgType.TEXT)
        msg.content = self._safe_get(raw, "Content")
        if msg.msg_type == MsgType.IMAGE:
            url = self._safe_get(raw, "PicUrl")
            if url:
                msg.media = MediaInfo(url=url)
        elif msg.msg_type == MsgType.VOICE:
            url = self._safe_get(raw, "Url")
            if url:
                msg.media = MediaInfo(url=url, format="amr")
        return msg

    def _convert_dingtalk(self, raw: Dict[str, Any]) -> UserMessage:
        msg = self._create_base_message(Channel.DINGTALK)
        msg.user_id = self._safe_get(raw, "senderId")
        msg.session_id = self._safe_get(raw, "conversationId")
        msg.msg_type = MsgType.TEXT
        text_val = self._safe_get_dict(raw, "text")
        if isinstance(text_val, dict):
            msg.content = self._safe_get(text_val, "content")
        else:
            msg.content = str(text_val) if text_val else ""
        nickname = self._safe_get(raw, "senderNick")
        msg.sender_info = SenderInfo(nickname=nickname or None)
        return msg

    def _convert_feishu(self, raw: Dict[str, Any]) -> UserMessage:
        msg = self._create_base_message(Channel.FEISHU)
        msg.user_id = self._safe_get(raw, "open_id")
        msg.session_id = self._safe_get(raw, "chat_id")
        msg.msg_type = raw.get("msg_type", raw.get("msgType", MsgType.TEXT))
        msg.content = self._safe_get(raw, "text")
        nickname = self._safe_get(raw, "sender_name")
        msg.sender_info = SenderInfo(nickname=nickname or None)
        return msg

    def _convert_default(self, raw: Dict[str, Any]) -> UserMessage:
        msg = self._create_base_message(Channel.OTHER)
        msg.user_id = self._safe_get(raw, "user_id", "userId")
        msg.session_id = self._safe_get(raw, "session_id", "sessionId")
        msg.msg_type = raw.get("msg_type", raw.get("msgType", MsgType.TEXT))
        msg.content = self._safe_get(raw, "content")
        return msg
