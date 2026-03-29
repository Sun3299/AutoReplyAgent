"""
MiniMax Provider 实现

通过 MiniMax API 调用 LLM。
"""

import time
import requests
from typing import List, Optional, Dict, Any

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    Message,
    MessageRole,
)

# 导入结构化日志
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from observability.logger import get_logger


class MiniMaxProvider(BaseLLMProvider):
    """
    MiniMax LLM Provider

    通过 MiniMax API 调用模型。

    配置参数：
    - api_key: API 密钥
    - base_url: API 地址（默认 https://mydamoxing.cn/v1）
    - model: 模型名称（默认 MiniMax-M2.7-32K）
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://mydamoxing.cn/v1",
        model: str = "MiniMax-M2.7-32K",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._logger = get_logger(f"llm.minimax")

    @property
    def name(self) -> str:
        """Provider 名称"""
        return "minimax"

    @property
    def default_config(self) -> LLMConfig:
        """默认配置"""
        return LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        对话补全（同步）

        Args:
            messages: 对话消息列表
            config: 配置

        Returns:
            LLMResponse
        """
        import json

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

        start_time = time.time()
        try:
            self._logger.info(
                "MiniMax API request",
                extra={
                    "model": config.model,
                    "message_count": len(messages),
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
            )

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=config.timeout,
            )
            latency_ms = (time.time() - start_time) * 1000

            self._logger.info(
                "MiniMax API response",
                extra={
                    "status_code": response.status_code,
                    "response_body_length": len(response.text),
                    "latency_ms": int(latency_ms),
                },
            )
            response.raise_for_status()

            result = response.json()

            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            finish_reason = result["choices"][0].get("finish_reason", "")

            self._logger.info(
                "MiniMax API response parsed",
                extra={
                    "content_length": len(content),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "finish_reason": finish_reason,
                    "latency_ms": int(latency_ms),
                },
            )

            return LLMResponse(
                content=content,
                usage=usage,
                model=config.model,
                finish_reason=finish_reason,
                raw_response=result,
            )

        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - start_time) * 1000
            self._logger.error(
                "MiniMax API request failed",
                extra={
                    "error": str(e),
                    "latency_ms": int(latency_ms),
                },
            )
            return LLMResponse(
                content="",
                error=f"请求失败: {str(e)}",
            )

    async def achat(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """异步对话补全"""
        # MiniMax SDK 不支持异步，这里简化处理
        return self.chat(messages, config)

    def _convert_message(self, message: Message) -> Dict[str, Any]:
        """
        转换消息格式

        将内部 Message 格式转换为 OpenAI API 格式。
        """
        return message.to_dict()


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM Provider - 用于测试

    不发送真实请求，返回预设的响应。
    """

    def __init__(self, response_content: str = "这是测试回复"):
        self._response_content = response_content

    @property
    def name(self) -> str:
        return "mock"

    @property
    def default_config(self) -> LLMConfig:
        return LLMConfig(model="mock")

    def chat(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        return LLMResponse(
            content=self._response_content,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            model="mock",
            finish_reason="stop",
        )

    async def achat(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        return self.chat(messages, config)

    def chat_stream(self, messages: List[Message], config: Optional[LLMConfig] = None):
        yield self._response_content
