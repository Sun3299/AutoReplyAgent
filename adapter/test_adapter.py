import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from adapter.models import UserMessage, MediaInfo, SenderInfo, Extension, Channel, MsgType
from adapter.adapter_core import MessageAdapter


class TestModels:
    def test_user_message_to_dict(self):
        msg = UserMessage(
            user_id="user_001",
            channel=Channel.WEB,
            session_id="session_001",
            msg_type=MsgType.TEXT,
            content="你好",
        )
        result = msg.to_dict()
        assert result["userId"] == "user_001"
        assert result["channel"] == "web"
        assert result["sessionId"] == "session_001"
        assert result["msgType"] == "text"
        assert result["content"] == "你好"
        assert "requestId" in result
        assert "createTime" in result

    def test_media_info_to_dict(self):
        media = MediaInfo(url="http://example.com/img.jpg", format="jpg")
        result = media.to_dict()
        assert result["url"] == "http://example.com/img.jpg"
        assert result["format"] == "jpg"
        assert "duration" not in result

    def test_sender_info_to_dict(self):
        sender = SenderInfo(nickname="张三", avatar="http://example.com/avatar.jpg")
        result = sender.to_dict()
        assert result["nickname"] == "张三"
        assert result["avatar"] == "http://example.com/avatar.jpg"
        assert "phone" not in result

    def test_extension_to_dict(self):
        ext = Extension(order_id="ORD001", product_id="PROD001")
        result = ext.to_dict()
        assert result["orderId"] == "ORD001"
        assert result["productId"] == "PROD001"
        assert "customData" in result


class TestMessageAdapter:
    def setup_method(self):
        self.adapter = MessageAdapter()

    def test_convert_web_message(self):
        raw = {
            "user_id": "web_user_001",
            "session_id": "web_session_001",
            "msg_type": "text",
            "content": "Hello web",
            "nickname": "WebUser",
            "avatar": "http://example.com/avatar.jpg",
        }
        print(f"\n>>> Web INPUT: {raw}")
        result = self.adapter.convert("web", raw)
        print(f">>> Web OUTPUT: {result}")
        assert result["channel"] == "web"
        assert result["userId"] == "web_user_001"
        assert result["content"] == "Hello web"
        assert result["senderInfo"]["nickname"] == "WebUser"

    def test_convert_wxmp_message(self):
        raw = {
            "FromUserName": "wx_user_001",
            "MsgId": "msg_001",
            "MsgType": "text",
            "Content": "Hello weixin",
        }
        print(f"\n>>> WXMP INPUT: {raw}")
        result = self.adapter.convert("wxmp", raw)
        print(f">>> WXMP OUTPUT: {result}")
        assert result["channel"] == "wxmp"
        assert result["userId"] == "wx_user_001"
        assert result["content"] == "Hello weixin"

    def test_convert_dingtalk_message(self):
        raw = {
            "senderId": "ding_user_001",
            "conversationId": "conv_001",
            "text": {"content": "Hello dingtalk"},
            "senderNick": "DingUser",
        }
        print(f"\n>>> DINGTALK INPUT: {raw}")
        result = self.adapter.convert("dingtalk", raw)
        print(f">>> DINGTALK OUTPUT: {result}")
        assert result["channel"] == "dingtalk"
        assert result["userId"] == "ding_user_001"
        assert result["content"] == "Hello dingtalk"
        assert result["senderInfo"]["nickname"] == "DingUser"

    def test_convert_feishu_message(self):
        raw = {
            "open_id": "feishu_user_001",
            "chat_id": "chat_001",
            "msg_type": "text",
            "text": "Hello feishu",
            "sender_name": "FeishuUser",
        }
        print(f"\n>>> FEISHU INPUT: {raw}")
        result = self.adapter.convert("feishu", raw)
        print(f">>> FEISHU OUTPUT: {result}")
        assert result["channel"] == "feishu"
        assert result["userId"] == "feishu_user_001"
        assert result["content"] == "Hello feishu"

    def test_convert_unknown_channel(self):
        raw = {
            "user_id": "unknown_user",
            "session_id": "unknown_session",
            "content": "未知渠道消息",
        }
        result = self.adapter.convert("custom_channel", raw)
        assert result["channel"] == "other"
        assert result["userId"] == "unknown_user"
        assert result["content"] == "未知渠道消息"

    def test_convert_with_media(self):
        raw = {
            "FromUserName": "wx_user_002",
            "MsgId": "msg_002",
            "MsgType": "image",
            "PicUrl": "http://example.com/image.jpg",
        }
        print(f"\n>>> MEDIA INPUT: {raw}")
        result = self.adapter.convert("wxmp", raw)
        print(f">>> MEDIA OUTPUT: {result}")
        assert result["msgType"] == "image"
        assert result["media"]["url"] == "http://example.com/image.jpg"

    def test_request_id_is_unique(self):
        raw = {"user_id": "u1", "content": "test"}
        result1 = self.adapter.convert("web", raw)
        result2 = self.adapter.convert("web", raw)
        assert result1["requestId"] != result2["requestId"]


class TestEdgeCases:
    def setup_method(self):
        self.adapter = MessageAdapter()

    def test_empty_message(self):
        """空消息体"""
        raw = {}
        print(f"\n>>> EMPTY INPUT: {raw}")
        result = self.adapter.convert("web", raw)
        print(f">>> EMPTY OUTPUT: {result}")
        assert result["content"] == ""
        assert result["channel"] == "web"

    def test_missing_user_id(self):
        """缺少userId"""
        raw = {"content": "only content"}
        result = self.adapter.convert("web", raw)
        assert result["userId"] == ""

    def test_wxmp_empty_text(self):
        """微信文本为空"""
        raw = {"FromUserName": "wx_001", "MsgId": "msg_1", "MsgType": "text", "Content": ""}
        print(f"\n>>> WXMP EMPTY TEXT INPUT: {raw}")
        result = self.adapter.convert("wxmp", raw)
        print(f">>> OUTPUT: {result}")
        assert result["content"] == ""

    def test_dingtalk_text_not_dict(self):
        """钉钉text字段不是dict"""
        raw = {"senderId": "ding_001", "conversationId": "conv_1", "text": "直接是字符串"}
        print(f"\n>>> DINGTALK NOT DICT INPUT: {raw}")
        result = self.adapter.convert("dingtalk", raw)
        print(f">>> OUTPUT: {result}")
        assert result["content"] == "直接是字符串"

    def test_null_values(self):
        """字段为null"""
        raw = {"user_id": None, "content": "test", "nickname": None}
        result = self.adapter.convert("web", raw)
        assert result["userId"] == ""
        assert "nickname" not in result["senderInfo"]

    def test_number_as_string(self):
        """数字类型字段"""
        raw = {"user_id": 12345, "content": 0}
        result = self.adapter.convert("web", raw)
        assert result["userId"] == "12345"
        assert result["content"] == "0"

    def test_special_chars(self):
        """特殊字符"""
        raw = {"content": "测试\n\t\r<>\"'&"}
        result = self.adapter.convert("web", raw)
        assert result["content"] == "测试\n\t\r<>\"'&"

    def test_very_long_content(self):
        """超长内容"""
        raw = {"content": "a" * 10000}
        result = self.adapter.convert("web", raw)
        assert len(result["content"]) == 10000

    def test_unicode_emoji(self):
        """emoji表情"""
        raw = {"content": "Hello 👋😊🎉"}
        result = self.adapter.convert("web", raw)
        assert result["content"] == "Hello 👋😊🎉"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
