"""
GPT-3.5 Provider 实现

通过 OpenAI API 调用 GPT-3.5 模型。
"""

import os
import requests
from typing import List, Optional, Dict, Any, AsyncIterator

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    Message,
    MessageRole,
)


class GPT35Provider(BaseLLMProvider):
    """
    GPT-3.5 LLM Provider
    
    通过 OpenAI API 调用 GPT-3.5 模型。
    
    配置参数：
    - api_key: API 密钥 (env: OPENAI_API_KEY)
    - model: 模型名称（默认 gpt-3.5-turbo）
    - base_url: API 地址（默认 https://api.openai.com/v1）
    """
    
    DEFAULT_MODEL = "gpt-3.5-turbo"
    API_BASE = "https://api.openai.com/v1"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = API_BASE,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
    
    @property
    def name(self) -> str:
        """Provider 名称"""
        return "gpt35"
    
    @property
    def default_config(self) -> LLMConfig:
        """默认配置"""
        return LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )
    
    def chat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        对话补全（同步）
        
        Args:
            messages: 对话消息列表
            config: 配置
            
        Returns:
            LLMResponse
        """
        config = config or self.default_config
        
        # 构建请求
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        # 转换消息格式
        openai_messages = [self._convert_message(m) for m in messages]
        
        data = {
            "model": config.model,
            "messages": openai_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=config.timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            finish_reason = result["choices"][0].get("finish_reason", "")
            
            return LLMResponse(
                content=content,
                usage=usage,
                model=config.model,
                finish_reason=finish_reason,
                raw_response=result,
            )
            
        except requests.exceptions.RequestException as e:
            return LLMResponse(
                content="",
                error=f"OpenAI API 请求失败: {str(e)}",
            )
    
    async def achat(
        self,
        messages: List[Message],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """异步对话补全"""
        # 简化为同步调用
        return self.chat(messages, config)
    
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
        config = config or self.default_config
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        openai_messages = [self._convert_message(m) for m in messages]
        
        data = {
            "model": config.model,
            "messages": openai_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": True,
        }
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=config.timeout,
                stream=True,
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_text = line.decode("utf-8")
                    if line_text.startswith("data: "):
                        data_str = line_text[6:]
                        if data_str == "[DONE]":
                            break
                        # 解析 SSE 数据
                        import json
                        try:
                            chunk = json.loads(data_str)
                            if chunk.get("choices"):
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                            
        except requests.exceptions.RequestException as e:
            return
    
    def _convert_message(self, message: Message) -> Dict[str, Any]:
        """
        转换消息格式
        
        将内部 Message 格式转换为 OpenAI API 格式。
        """
        return {
            "role": message.role.value,
            "content": message.content,
        }