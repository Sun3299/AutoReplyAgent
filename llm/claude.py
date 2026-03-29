"""
Claude Provider 实现

通过 Anthropic API 调用 Claude 模型。
"""

import os
import time
import requests
from typing import List, Optional, Dict, Any, AsyncIterator

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMConfig,
    Message,
    Usage,
)

# 导入结构化日志
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from observability.logger import get_logger


class ClaudeProvider(BaseLLMProvider):
    """
    Claude LLM Provider

    通过 Anthropic API 调用 Claude 模型。

    配置参数：
    - api_key: API 密钥 (env: ANTHROPIC_API_KEY)
    - model: 模型名称（默认 claude-sonnet-4-20250514）
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    API_BASE = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self._logger = get_logger(f"llm.claude")

    @property
    def name(self) -> str:
        """Provider 名称"""
        return "claude"

    @property
    def default_config(self) -> LLMConfig:
        """默认配置"""
        return LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.API_BASE,
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
        config = config or self.default_config

        # 构建请求
        url = f"{self.API_BASE}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }

        # 转换消息格式
        anthropic_messages = [self._convert_message(m) for m in messages]

        data = {
            "model": config.model,
            "messages": anthropic_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        # 添加 top_p 如果不是默认值
        if config.top_p != 1.0:
            data["top_p"] = config.top_p

        start_time = time.time()
        try:
            self._logger.info(
                "Claude API request",
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

            response.raise_for_status()
            result = response.json()

            content = result["content"][0]["text"]
            usage = Usage(
                input=result.get("usage", {}).get("input_tokens", 0),
                output=result.get("usage", {}).get("output_tokens", 0),
            )
            finish_reason = result.get("stop_reason", "stop")

            self._logger.info(
                "Claude API response",
                extra={
                    "content_length": len(content),
                    "input_tokens": usage.input,
                    "output_tokens": usage.output,
                    "total_tokens": usage.input + usage.output,
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
                "Claude API request failed",
                extra={
                    "error": str(e),
                    "latency_ms": int(latency_ms),
                },
            )
            return LLMResponse(
                content="",
                error=f"Claude API 请求失败: {str(e)}",
            )

    async def achat(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """异步对话补全"""
        # 简化为同步调用
        return self.chat(messages, config)

    def chat_stream(
        self, messages: List[Message], config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """
        流式对话补全

        注意：Anthropic API 不支持流式响应，此处使用模拟实现
        """
        config = config or self.default_config

        url = f"{self.API_BASE}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }

        anthropic_messages = [self._convert_message(m) for m in messages]

        data = {
            "model": config.model,
            "messages": anthropic_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        if config.top_p != 1.0:
            data["top_p"] = config.top_p

        start_time = time.time()
        try:
            self._logger.info(
                "Claude API chat_stream request",
                extra={
                    "model": config.model,
                    "message_count": len(messages),
                },
            )

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
                            if chunk.get("type") == "content_block_delta":
                                delta = chunk.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue

            latency_ms = (time.time() - start_time) * 1000
            self._logger.info(
                "Claude API chat_stream completed",
                extra={"latency_ms": int(latency_ms)},
            )

        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - start_time) * 1000
            self._logger.error(
                "Claude API chat_stream failed",
                extra={"error": str(e), "latency_ms": int(latency_ms)},
            )
            return

    def _convert_message(self, message: Message) -> Dict[str, Any]:
        """
        转换消息格式

        将内部 Message 格式（UserMessage/AssistantMessage/ToolResultMessage/SystemMessage）
        转换为 Anthropic API 格式。
        """
        return message.to_dict()
