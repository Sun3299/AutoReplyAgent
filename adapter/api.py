from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from adapter.adapter_core import MessageAdapter

app = FastAPI(title="AI客服智能体 - Adapter层")
adapter = MessageAdapter()


class IncomingMessage(BaseModel):
    channel: str
    data: Dict[str, Any]


@app.post("/api/message")
async def receive_message(message: IncomingMessage):
    try:
        standardized = adapter.convert(message.channel, message.data)
        return {"status": "success", "data": standardized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Adapter 测试工具</title>
        <style>
            body { font-family: Arial; padding: 20px; background: #f5f5f5; }
            .container { max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; }
            .section { margin: 20px 0; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            select, textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            textarea { height: 150px; font-family: monospace; }
            button { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
            button:hover { background: #0056b3; }
            .result { margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 4px; border: 1px solid #ddd; }
            .result h3 { margin-top: 0; }
            pre { background: #272822; color: #f8f8f2; padding: 15px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; }
            .tabs { margin-bottom: 10px; }
            .tab { padding: 8px 16px; background: #eee; border: 1px solid #ddd; cursor: pointer; display: inline-block; }
            .tab.active { background: #007bff; color: white; }
            .presets { margin-bottom: 10px; }
            .preset-btn { padding: 6px 12px; margin-right: 5px; background: #28a745; color: white; border: none; border-radius: 3px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Adapter 可视化测试工具</h1>
            <div class="section">
                <label>选择渠道:</label>
                <select id="channel">
                    <option value="web">网页 (web)</option>
                    <option value="wxmp">微信公众号 (wxmp)</option>
                    <option value="dingtalk">钉钉 (dingtalk)</option>
                    <option value="feishu">飞书 (feishu)</option>
                    <option value="custom">自定义 (other)</option>
                </select>
            </div>
            <div class="section">
                <label>预设模板:</label>
                <div class="presets">
                    <button class="preset-btn" onclick="loadPreset('web_text')">网页-文本</button>
                    <button class="preset-btn" onclick="loadPreset('web_image')">网页-图片</button>
                    <button class="preset-btn" onclick="loadPreset('wxmp_text')">微信-文本</button>
                    <button class="preset-btn" onclick="loadPreset('wxmp_image')">微信-图片</button>
                    <button class="preset-btn" onclick="loadPreset('dingtalk_text')">钉钉-文本</button>
                    <button class="preset-btn" onclick="loadPreset('feishu_text')">飞书-文本</button>
                </div>
            </div>
            <div class="section">
                <label>原始消息 JSON:</label>
                <textarea id="rawJson">{"user_id": "user_001", "session_id": "session_001", "content": "你好"}</textarea>
            </div>
            <button onclick="convert()">转换</button>
            <div class="result" id="result" style="display:none">
                <h3>标准 UserMessage 输出:</h3>
                <pre id="output"></pre>
            </div>
        </div>
        <script>
            const presets = {
                web_text: {"channel":"web","data":{"user_id":"user_001","session_id":"sess_001","content":"你好，我想查询订单","nickname":"张三"}},
                web_image: {"channel":"web","data":{"user_id":"user_001","session_id":"sess_001","msg_type":"image","media_url":"http://example.com/img.jpg","format":"jpg"}},
                wxmp_text: {"channel":"wxmp","data":{"FromUserName":"wx_user_001","MsgId":"msg_123","MsgType":"text","Content":"查询物流"}},
                wxmp_image: {"channel":"wxmp","data":{"FromUserName":"wx_user_001","MsgId":"msg_124","MsgType":"image","PicUrl":"http://example.com/pic.jpg"}},
                dingtalk_text: {"channel":"dingtalk","data":{"senderId":"ding_001","conversationId":"conv_001","text":{"content":"我要退款"},"senderNick":"李四"}},
                feishu_text: {"channel":"feishu","data":{"open_id":"feishu_001","chat_id":"chat_001","msg_type":"text","text":"订单问题","sender_name":"王五"}}
            };
            function loadPreset(name) {
                const p = presets[name];
                document.getElementById('channel').value = p.channel;
                document.getElementById('rawJson').value = JSON.stringify(p.data, null, 2);
            }
            async function convert() {
                const channel = document.getElementById('channel').value;
                const rawJson = document.getElementById('rawJson').value;
                try {
                    const data = JSON.parse(rawJson);
                    const res = await fetch('/api/message', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({channel: channel, data: data})
                    });
                    const json = await res.json();
                    document.getElementById('output').textContent = JSON.stringify(json, null, 2);
                    document.getElementById('result').style.display = 'block';
                } catch(e) {
                    alert('JSON格式错误: ' + e.message);
                }
            }
        </script>
    </body>
    </html>
    """