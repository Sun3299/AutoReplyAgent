#!/usr/bin/env python
"""
控制台对话 autoreply
通过 HTTP 调用网关，保持模型在服务器内存中
"""
import requests
import sys
import time

AUTOREPLY_URL = "http://localhost:8000/v1/chat"


def chat(message, user_id="console_user", session_id="console_session"):
    """发送消息给 autoreply"""
    payload = {
        "requestId": f"req_{int(time.time() * 1000)}",
        "userId": user_id,
        "channel": "xianyu",
        "sessionId": session_id,
        "msgType": "text",
        "content": message,
        "createTime": "2026-03-27 12:00:00"
    }
    
    try:
        resp = requests.post(AUTOREPLY_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            return result.get("content", "无回复")
        else:
            return f"请求失败: {resp.status_code}"
    except Exception as e:
        return f"请求异常: {e}"


def main():
    print("=" * 50)
    print("控制台对话 autoreply")
    print("=" * 50)
    print("输入消息直接对话，quit 或 exit 退出")
    print()
    
    session_id = f"session_{int(time.time() * 1000)}"
    
    while True:
        try:
            message = input("你: ").strip()
        except KeyboardInterrupt:
            print("\n退出")
            break
        
        if not message:
            continue
        
        if message.lower() in ("quit", "exit", "q"):
            print("退出")
            break
        
        print("AI: ", end="", flush=True)
        reply = chat(message, session_id=session_id)
        print(reply)
        print()


if __name__ == "__main__":
    main()
