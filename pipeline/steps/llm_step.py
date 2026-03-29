"""
LLM Step - LLM生成步骤

使用 LLM Fallback 链生成响应。

输入：
    - ctx.request: 用户消息
    - ctx.get("rag_results"): RAG 检索结果
    - ctx.get("tool_results"): 工具执行结果

输出：
    - ctx.set("llm_response", response.content): LLM 响应内容
    - ctx.set("llm_model_used", model_name): 实际使用的模型
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, TYPE_CHECKING
import time

from pipeline.step import Step, StepResult, StepType
from llm.base import (
    Message,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
    TextContent,
    LLMConfig,
)
from llm.fallback import ModelFallbackChain

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineContext


class LlmStep(Step):
    """
    LLM 生成步骤

    负责：
    1. 构建 prompt
    2. 调用 LLM Fallback 链
    3. 记录使用的模型

    使用示例：
        step = LlmStep()
        result = step.execute(ctx)
    """

    def __init__(
        self,
        fallback_chain: Optional[ModelFallbackChain] = None,
        default_config: Optional[LLMConfig] = None,
    ):
        """
        初始化 LLM 步骤

        Args:
            fallback_chain: LLM Fallback 链，默认创建 MiniMax → Claude → GPT-3.5 链
            default_config: 默认 LLM 配置
        """
        super().__init__("llm_step", StepType.LLM, optional=False, timeout=60)
        self._fallback_chain = fallback_chain
        self._default_config = default_config or LLMConfig()

    @property
    def fallback_chain(self) -> ModelFallbackChain:
        """获取 Fallback 链"""
        if self._fallback_chain is None:
            # 延迟创建，避免循环导入
            from llm.providers import MiniMaxProvider, MockLLMProvider
            from llm.claude import ClaudeProvider
            from llm.gpt35 import GPT35Provider
            from config.settings import get_settings

            settings = get_settings()
            api_key = settings.llm_api_key or "mock"
            base_url = settings.llm_base_url or "https://mydamoxing.cn/v1"
            model = settings.llm_model or "MiniMax-M2.7-highspeed"

            # 使用真实配置的 MiniMax，Mock 其他作为 fallback
            self._fallback_chain = ModelFallbackChain(
                [
                    MiniMaxProvider(api_key=api_key, base_url=base_url, model=model),
                    # MockClaudeProvider(api_key="mock") as fallback
                    MockLLMProvider(response_content="Claude 暂时不可用"),
                ]
            )

            # 保存 settings 供后续使用
            self._settings = settings
        return self._fallback_chain

    def _build_llm_config(self) -> LLMConfig:
        """从 settings 构建完整的 LLMConfig"""
        from config.settings import get_settings

        settings = getattr(self, "_settings", None) or get_settings()

        return LLMConfig(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            top_p=settings.llm_top_p,
            timeout=settings.llm_timeout,
        )

    def _do_execute(self, ctx: "PipelineContext") -> StepResult:
        """
        执行 LLM 生成

        Args:
            ctx: Pipeline上下文

        Returns:
            StepResult: 执行结果
        """
        print("[LLM STEP] Starting execution", flush=True)
        start_time = time.time()

        try:
            # 检查是否应该终止
            print(
                f"[LLM STEP] should_terminate={ctx.get('should_terminate')}", flush=True
            )
            if ctx.get("should_terminate"):
                return StepResult(
                    success=True,
                    data={"message": "Skipped due to termination"},
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=time.time() - start_time,
                    metadata={
                        "skipped": True,
                        "reason": ctx.get("terminate_reason", "Unknown"),
                        "duration_ms": int((time.time() - start_time) * 1000),
                    },
                )

            # 构建消息
            messages = self._build_messages(ctx)

            # 调用 LLM（传入完整 config）
            print("[LLM STEP] Calling fallback chain...", flush=True)
            config = self._build_llm_config()
            response = self.fallback_chain.chat(messages, config)
            print(
                f"[LLM STEP] Response - content='{response.content[:100] if response.content else '(empty)'}', error='{response.error}'",
                flush=True,
            )
            print(f"[LLM STEP] Response metadata: {response.metadata}", flush=True)

            # 提取模型信息
            model_used = "unknown"
            if response.metadata:
                model_used = response.metadata.get("model_used", "unknown")

            # 检查是否成功
            if response.error:
                print(f"[LLM ERROR] {response.error}")
                duration = time.time() - start_time
                return StepResult(
                    success=False,
                    error=f"LLM failed: {response.error}",
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=duration,
                    metadata={
                        "model_used": model_used,
                        "duration_ms": int(duration * 1000),
                    },
                )

            print(
                f"[LLM RESPONSE] content='{response.content[:100] if response.content else '(empty)'}...'"
            )
            # 设置到上下文
            ctx.set("llm_response", response.content)
            ctx.set("llm_model_used", model_used)

            duration = time.time() - start_time

            return StepResult(
                success=True,
                data={
                    "content": response.content,
                    "model_used": model_used,
                    "usage": response.usage,
                },
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "model_used": model_used,
                    "duration_ms": int(duration * 1000),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"LlmStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                },
            )

    def _build_messages(self, ctx: "PipelineContext") -> List[Message]:
        """
        构建消息列表

        消息结构：
        1. System: 系统提示 + 商品信息
        2. 历史对话（user/assistant 交替，无 RAG）
        3. 当前消息（包含 RAG 参考资料 + 用户问题）

        Args:
            ctx: Pipeline上下文

        Returns:
            消息列表
        """
        messages: List[Message] = []

        # ========== 1. System: 系统提示 ==========
        system_prompt = ctx.get("system_prompt")
        if system_prompt:
            prompt = system_prompt
        else:
            prompt = """你是一个客服助手。
        回答用户问题时要：
        1. 用自己的话简洁回答，不要列点
        2. 如果有相关知识，结合知识回答，但要用自然的方式，不要说"根据知识..."
        3. 口语化、亲切、有礼貌"""

        # 添加商品信息
        extension = ctx.get("extension", {})
        item_info = (
            extension.get("item_info", "") if isinstance(extension, dict) else ""
        )
        if item_info:
            prompt = f"{prompt}\n\n【当前商品信息】\n{item_info}"

        messages.append(SystemMessage(content=prompt))

        # ========== 2. 历史对话 ==========
        history = ctx.get("history_messages", [])
        for hist_msg in history:
            if hasattr(hist_msg, "role"):
                role = hist_msg.role
                content = hist_msg.content if hasattr(hist_msg, "content") else ""
            else:
                role = hist_msg.get("role", "user")
                content = hist_msg.get("content", "")

            if role != "user" and role != "assistant":
                role = "user" if role == "user" else "assistant"

            if role == "user":
                messages.append(UserMessage(content=content))
            else:
                messages.append(AssistantMessage(content=[TextContent(text=content)]))

        # ========== 3. 当前消息（RAG 参考资料 + 用户问题） ==========
        rag_results = ctx.get("rag_results", [])
        rag_context = self._format_rag_results(rag_results) if rag_results else ""

        # 检查是否需要澄清（clarify/ambiguous）
        needs_clarify = ctx.get("needs_clarify", False)
        clarify_question = ctx.get("clarify_question", "")

        current_content = ""
        if needs_clarify:
            # clarify/ambiguous 场景：让 LLM 帮助用户明确意图
            clarify_hint = (
                "【注意】用户表达可能不够清晰或有歧义，"
                "请友好地询问用户明确，以帮助您更好地理解用户需求。"
            )
            if rag_context:
                current_content = f"{clarify_hint}\n\n参考资料：\n{rag_context}\n\n问题：{ctx.request}"
            else:
                current_content = f"{clarify_hint}\n\n问题：{ctx.request}"
        elif rag_context:
            current_content = f"参考资料：\n{rag_context}\n\n问题：{ctx.request}"
        else:
            current_content = ctx.request

        messages.append(UserMessage(content=current_content))

        return messages

    def _format_rag_results(self, rag_results: List[Any]) -> str:
        """
        格式化 RAG 结果为带来源标识的字符串

        格式：[来源|置信度] 内容；[来源|置信度] 内容
        """
        if not rag_results:
            return ""

        parts = []
        for result in rag_results:
            if isinstance(result, str):
                parts.append(result)
            elif isinstance(result, dict):
                content = result.get("content", str(result))
                source = result.get("source", "")
                score = result.get("score", None)

                if source and score is not None:
                    parts.append(f"[{source}|{score:.2f}] {content}")
                elif source:
                    parts.append(f"[{source}] {content}")
                else:
                    parts.append(content)
            else:
                parts.append(str(result))

        return "；".join(parts)

    def _format_tool_results(self, tool_results: List[Dict[str, Any]]) -> str:
        """格式化工具结果"""
        if not tool_results:
            return "无工具查询结果"

        formatted = []
        for result in tool_results:
            tool_name = result.get("tool_name", "unknown")
            success = result.get("success", False)
            data = result.get("data")
            error = result.get("error", "")

            if success:
                content = str(data) if data else "无数据"
                formatted.append(f"【{tool_name}】查询成功: {content}")
            else:
                formatted.append(f"【{tool_name}】查询失败: {error}")

        return "\n".join(formatted)
