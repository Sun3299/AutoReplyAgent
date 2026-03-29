"""
Output Step - 输出合成步骤

使用 OutputSynthesizer 合成最终回复。

输入：
    - ctx.get("rag_results"): RAG 检索结果
    - ctx.get("tool_results"): 工具执行结果
    - ctx.get("llm_response"): LLM 响应
    - ctx.get("intent"): 意图信息（可选）

输出：
    - ctx.set("final_response", result.content): 最终回复
    - ctx.set("output_source", result.source): 来源标记
"""

from __future__ import annotations

from typing import Optional, Dict, Any, TYPE_CHECKING
import time

from pipeline.step import Step, StepResult, StepType
from output.synthesizer import OutputSynthesizer, OutputContext, OutputFormat
from agent.models import AgentRecommendation

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineContext


class OutputStep(Step):
    """
    输出合成步骤

    负责：
    1. 收集 RAG 结果、工具结果、LLM 输出
    2. 使用 OutputSynthesizer 合成最终回复
    3. 应用格式控制和质量过滤

    使用示例：
        step = OutputStep()
        result = step.execute(ctx)
    """

    def __init__(
        self,
        synthesizer: Optional[OutputSynthesizer] = None,
        default_format: OutputFormat = OutputFormat.TEXT,
    ):
        """
        初始化 Output 步骤

        Args:
            synthesizer: 输出合成器实例
            default_format: 默认输出格式
        """
        super().__init__("output_step", StepType.OUTPUT, optional=False, timeout=30)
        self._synthesizer = synthesizer
        self._default_format = default_format

    @property
    def synthesizer(self) -> OutputSynthesizer:
        """获取合成器实例"""
        if self._synthesizer is None:
            # 延迟创建
            from output.synthesizer import get_synthesizer

            self._synthesizer = get_synthesizer()
        return self._synthesizer

    def _do_execute(self, ctx: "PipelineContext") -> StepResult:
        """
        执行输出合成

        Args:
            ctx: Pipeline上下文

        Returns:
            StepResult: 执行结果
        """
        start_time = time.time()

        try:
            output_context = self._build_output_context(ctx)

            if ctx.get("needs_clarify"):
                clarify_question = ctx.get("clarify_question", "请提供更多信息")
                final_response = clarify_question
                output_source = "clarify"
            else:
                synth_result = self.synthesizer.synthesize(output_context)
                final_response = synth_result.content
                output_source = synth_result.source

            if ctx.get("should_terminate"):
                terminate_reason = ctx.get("terminate_reason", "")
                if terminate_reason:
                    final_response = terminate_reason
                    output_source = "terminate"

            final_response = self._apply_recommendation_postprocess(ctx, final_response)

            # 如果是新会话，加欢迎语
            if ctx.get("is_new_session"):
                welcome = ctx.get("welcome_message", "")
                if welcome:
                    final_response = f"{welcome}\n\n{final_response}"

            # 设置到上下文
            ctx.set("final_response", final_response)
            ctx.set("output_source", output_source)

            duration = time.time() - start_time

            return StepResult(
                success=True,
                data={
                    "content": final_response,
                    "source": output_source,
                },
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "output_source": output_source,
                    "duration_ms": int(duration * 1000),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"OutputStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                },
            )

    def _apply_recommendation_postprocess(
        self, ctx: "PipelineContext", current_response: str
    ) -> str:
        """
        根据 action 生成推荐话术后处理

        Args:
            ctx: Pipeline上下文
            current_response: 当前回复

        Returns:
            处理后的回复
        """
        recommendation = ctx.get("recommendation")
        if not recommendation:
            return current_response

        if isinstance(recommendation, dict):
            action = recommendation.get("action", "none")
            product_name = recommendation.get("product_name", "")
            reason = recommendation.get("reason", "")
        elif isinstance(recommendation, AgentRecommendation):
            action = recommendation.action
            product_name = recommendation.product_name or ""
            reason = recommendation.reason or ""
        else:
            return current_response

        if action == "none" or not action:
            return current_response

        user_context = ctx.get("user_context", {})

        if action == "recommend":
            return (
                f"根据您的情况，推荐您了解「{product_name}」。"
                f"{reason}"
                f"有什么可以帮您进一步了解的吗？"
            )
        elif action == "follow_up":
            return (
                f"您好！之前您咨询过「{product_name}」，"
                f"现在有新的动态，{reason}"
                f"要了解一下吗？"
            )
        elif action == "transfer":
            return "抱歉，您的问题我无法解答，已为您转接人工客服。"
        else:
            return current_response

    def _build_output_context(self, ctx: "PipelineContext") -> OutputContext:
        """
        构建输出上下文

        Args:
            ctx: Pipeline上下文

        Returns:
            OutputContext
        """
        rag_results = ctx.get("rag_results", [])
        if isinstance(rag_results, list):
            rag_contents = []
            for r in rag_results:
                if isinstance(r, str):
                    rag_contents.append(r)
                elif isinstance(r, dict):
                    content = r.get("content", r.get("text", str(r)))
                    rag_contents.append(content)
                else:
                    rag_contents.append(str(r))
        else:
            rag_contents = [str(rag_results)] if rag_results else []

        tool_results = ctx.get("tool_results", [])
        tool_dicts = []
        for r in tool_results:
            if isinstance(r, dict):
                tool_dicts.append(r)
            else:
                tool_dicts.append({"data": str(r), "success": True})

        llm_output = ctx.get("llm_response", "")

        intent = ctx.get("intent")
        intent_str = ""
        if intent:
            if hasattr(intent, "to_dict"):
                intent_dict = intent.to_dict()
                intent_str = intent_dict.get("intentType", "")
            else:
                intent_str = str(intent)

        confidence = 0.0
        if intent and hasattr(intent, "confidence"):
            confidence = intent.confidence

        # 获取会话状态
        session_state = ctx.get("session_state", {})

        return OutputContext(
            rag_results=rag_contents,
            tool_results=tool_dicts,
            llm_output=llm_output,
            intent=intent_str,
            confidence=confidence,
            session_state=session_state,
        )
