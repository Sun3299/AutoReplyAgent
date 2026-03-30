"""
Agent Step - Agent规划步骤

使用 Agent 进行意图识别和执行规划。

输入：
    - ctx.request: 用户消息
    - ctx.get("session_state"): 会话状态

输出：
    - ctx.set("intent", intent): 识别到的意图
    - ctx.set("execution_plan", plan): 执行计划
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import time

from pipeline.step import Step, StepResult, StepType
from agent.agent_core import Agent, AgentInput, SessionInfo
from agent.models import Intent
from tools.user_profile_tool import UserProfileTool
from config.channel_manager import load_prompt
from context.session_handler import SessionHandler


class AgentStep(Step):
    """
    Agent规划步骤

    负责：
    1. 意图识别
    2. 执行规划

    使用示例：
        step = AgentStep()
        result = step.execute(ctx)
    """

    def __init__(self, agent: Optional[Agent] = None):
        """
        初始化 Agent 步骤

        Args:
            agent: Agent实例，默认创建新实例
        """
        super().__init__("agent_step", StepType.AGENT, optional=False, timeout=30)
        self._agent = agent

    @property
    def agent(self) -> Agent:
        """获取 Agent 实例"""
        if self._agent is None:
            self._agent = Agent()
        return self._agent

    def _do_execute(self, ctx: "PipelineContext") -> StepResult:
        """
        执行 Agent 规划

        Args:
            ctx: Pipeline上下文

        Returns:
            StepResult: 执行结果
        """
        start_time = time.time()

        try:
            # =========================================================
            # 1. 加载用户画像 (新会话时)
            # =========================================================
            if ctx.get("is_new_session"):
                user_profile_tool = UserProfileTool()
                profile_result = user_profile_tool.execute(
                    user_id=ctx.user_id, channel=ctx.get("channel", "web")
                )
                ctx.set("user_context", profile_result.data)

            # =========================================================
            # 2. 加载平台 prompt（从 channel 配置读取）
            # =========================================================
            channel = ctx.get("channel", "web")
            prompt = load_prompt(channel)
            ctx.set("system_prompt", prompt)
            ctx.set("welcome_message", "您好！有什么可以帮您的？")

            # =========================================================
            # 3. 加载对话历史 (Sliding Window)
            # =========================================================
            session_key = ctx.get("session_key")
            channel = ctx.get("channel", "web")
            history_messages = []
            if session_key:
                # 添加 channel 前缀，避免不同渠道的 session 冲突
                prefixed_session_key = f"{channel}:{session_key}"
                session_handler = SessionHandler()

                # 先尝试从 SessionManager 内存读取
                rounds, _ = session_handler.get_rounds(
                    prefixed_session_key, keep_rounds=None
                )
                if rounds:
                    history_messages = rounds
                else:
                    # 内存没有，从文件读取（跨进程持久化）
                    file_records = session_handler.get_session_history_from_file(
                        channel, session_key, limit=0
                    )
                    if file_records:
                        # 转换文件格式到 rounds 格式
                        # 文件中存储的 request_id 现在是真实的 trace_id
                        history_messages = [
                            {
                                "round": idx // 2 + 1,
                                "requestId": r.get("request_id", f"file_{idx}"),
                                "timestamp": r.get("timestamp", ""),
                                "role": r.get("type", "user"),
                                "content": r.get("content", ""),
                            }
                            for idx, r in enumerate(file_records)
                        ]
            ctx.set("history_messages", history_messages)

            # =========================================================
            # 4. 构建 SessionInfo
            # =========================================================
            user_message = ctx.request
            session_state = ctx.get("session_state", {}) or {}

            session_info = SessionInfo(
                session_id=session_key or ctx.get("session_id", ""),
                user_id=ctx.user_id,
                state=session_state,
                rounds=history_messages,
            )

            agent_input = AgentInput(
                user_message=user_message,
                session_info=session_info,
                channel=ctx.get("channel", "web"),
            )

            # 执行 Agent
            agent_output = self.agent.run(agent_input)

            # 计算耗时
            duration = time.time() - start_time

            # 提取意图信息
            intent = agent_output.intent
            execution_plan = agent_output.execution_plan

            # 判断是否需要终止
            should_terminate = agent_output.should_terminate
            terminate_reason = agent_output.terminate_reason

            # 设置输出到上下文
            ctx.set("intent", intent)
            ctx.set("execution_plan", execution_plan)
            ctx.set("needs_clarify", agent_output.needs_clarify)
            ctx.set("clarify_question", agent_output.clarify_question)

            # 如果需要终止，设置终止标志
            if should_terminate:
                ctx.set("should_terminate", True)
                ctx.set("terminate_reason", terminate_reason)

            # 构建结果数据
            result_data = {
                "intent": intent.to_dict() if intent else None,
                "execution_plan": [p.to_dict() for p in execution_plan],
                "needs_clarify": agent_output.needs_clarify,
                "clarify_question": agent_output.clarify_question,
                "should_terminate": should_terminate,
                "terminate_reason": terminate_reason,
            }

            return StepResult(
                success=True,
                data=result_data,
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "model_used": "agent_core",
                    "duration_ms": int(duration * 1000),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            return StepResult(
                success=False,
                error=f"AgentStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                },
            )
