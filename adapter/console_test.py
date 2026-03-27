"""
交互式Adapter测试工具
用法: python adapter/console_test.py
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter.adapter_core import MessageAdapter

adapter = MessageAdapter()

PRESETS = {
    "1": ("web 文本", "web", {"user_id": "user_001", "session_id": "sess_001", "content": "你好", "nickname": "张三"}),
    "2": ("web 图片", "web", {"user_id": "user_001", "session_id": "sess_001", "msg_type": "image", "media_url": "http://example.com/img.jpg", "format": "jpg"}),
    "3": ("微信文本", "wxmp", {"FromUserName": "wx_user_001", "MsgId": "msg_123", "MsgType": "text", "Content": "查询订单"}),
    "4": ("微信图片", "wxmp", {"FromUserName": "wx_user_001", "MsgId": "msg_124", "MsgType": "image", "PicUrl": "http://example.com/pic.jpg"}),
    "5": ("钉钉文本", "dingtalk", {"senderId": "ding_001", "conversationId": "conv_001", "text": {"content": "我要退款"}, "senderNick": "李四"}),
    "6": ("飞书文本", "feishu", {"open_id": "feishu_001", "chat_id": "chat_001", "msg_type": "text", "text": "订单问题", "sender_name": "王五"}),
}

def main():
    print("\n=== Adapter 交互式测试工具 ===")
    print("输入预设编号或自定义JSON进行测试\n")
    print("预设模板:")
    for k, (name, _, _) in PRESETS.items():
        print(f"  {k}. {name}")
    print("  7. 自定义输入")
    print("  q. 退出\n")
    
    while True:
        choice = input("请选择 > ").strip()
        
        if choice.lower() == 'q':
            break
        
        if choice in PRESETS:
            name, channel, raw = PRESETS[choice]
            print(f"\n>>> 渠道: {channel}")
            print(f">>> 原始消息: {json.dumps(raw, ensure_ascii=False)}")
            result = adapter.convert(channel, raw)
            print(f">>> 标准输出:\n{json.dumps(result, ensure_ascii=False, indent=2)}\n")
        elif choice == '7':
            channel = input("输入渠道 (web/wxmp/dingtalk/feishu): ").strip()
            raw_str = input("输入JSON消息: ").strip()
            try:
                raw = json.loads(raw_str)
                result = adapter.convert(channel, raw)
                print(f">>> 标准输出:\n{json.dumps(result, ensure_ascii=False, indent=2)}\n")
            except json.JSONDecodeError as e:
                print(f"JSON格式错误: {e}\n")
        else:
            print("无效选择\n")

if __name__ == "__main__":
    main()