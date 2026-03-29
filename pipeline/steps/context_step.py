"""
Context Step - 上下文管理步骤

管理会话状态、缓存和异步数据库写入。

输入：
    - ctx.request: 用户消息
    - ctx.get("final_response"): 助手回复
    - ctx.get("session_id"): 会话ID（可选）
    - ctx.get("intent"): 意图信息（可选）

输出：
    - ctx.set("session_updated", True): 会话已更新标记
"""

from __future__ import annotations

from typing import Optional, Dict, Any, TYPE_CHECKING
import time
import asyncio
import threading

from pipeline.step import Step, StepResult, StepType
from session.session_manager import SessionManager
from context.manager import ContextManager

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineContext


class ContextStep(Step):
    """
    上下文管理步骤

    负责：
    1. 保存用户消息和助手回复到会话
    2. 更新会话状态（如意图）
    3. 触发异步数据库写入
    4. 管理上下文生命周期

    使用示例：
        step = ContextStep()
        result = step.execute(ctx)
    """

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        context_manager: Optional[ContextManager] = None,
        async_db_write: bool = True,
    ):
        """
        初始化 Context 步骤

        Args:
            session_manager: SessionManager 实例
            context_manager: ContextManager 实例
            async_db_write: 是否启用异步数据库写入
        """
        super().__init__("context_step", StepType.CONTEXT, optional=True, timeout=30)
        self._session_manager = session_manager
        self._context_manager = context_manager
        self._async_db_write = async_db_write
        self._pending_writes: Dict[str, Any] = {}

    @property
    def session_manager(self) -> SessionManager:
        """获取 SessionManager 实例"""
        if self._session_manager is None:
            self._session_manager = SessionManager()
        return self._session_manager

    @property
    def context_manager(self) -> ContextManager:
        """获取 ContextManager 实例"""
        if self._context_manager is None:
            self._context_manager = ContextManager()
        return self._context_manager

    def _do_execute(self, ctx: "PipelineContext") -> StepResult:
        """
        执行上下文管理

        Args:
            ctx: Pipeline上下文

        Returns:
            StepResult: 执行结果
        """
        print(
            f"[CONTEXT STEP] Starting execution for session: {ctx.get('session_key')}"
        )
        start_time = time.time()

        try:
            # 获取会话ID和渠道
            session_id = ctx.get("session_key")  # Gateway 存的是 session_key
            channel = ctx.get("channel", "web")
            print(
                f"[CONTEXT DEBUG] step started: session_id={session_id}, channel={channel}",
                flush=True,
            )

            # 如果没有会话ID，尝试创建或跳过
            if not session_id:
                print(
                    "[CONTEXT DEBUG] no session_id, trying to get from user_id",
                    flush=True,
                )
                # 尝试从 user_id 获取已有会话
                user_id = ctx.user_id
                if user_id:
                    sessions = self.session_manager.get_user_sessions(user_id)
                    if sessions:
                        session_id = sessions[0].session_id

            # 如果仍然没有会话ID，跳过会话保存
            if not session_id:
                duration = time.time() - start_time
                return StepResult(
                    success=True,
                    data={"message": "No session_id, skipping session save"},
                    step_name=self.name,
                    step_type=self.step_type.value,
                    duration=duration,
                    metadata={
                        "skipped": True,
                        "reason": "no_session_id",
                        "duration_ms": int(duration * 1000),
                    },
                )

            # 添加 channel 前缀，避免不同渠道的 session 冲突
            prefixed_session_id = f"{channel}:{session_id}"

            # 如果 session 不存在，先创建
            if not self.session_manager.session_exists(prefixed_session_id):
                self.session_manager.create_session(
                    user_id=ctx.user_id or "unknown",
                    channel=channel,
                    session_type="general",
                    session_key=prefixed_session_id,
                )

            # 保存用户消息
            user_message = ctx.request
            assistant_message = ctx.get("final_response", "")

            print(f"[CONTEXT DEBUG] Saving user message: {user_message}")
            print(f"[CONTEXT DEBUG] prefixed_session_id: {prefixed_session_id}")
            print(f"[CONTEXT DEBUG] session_manager id: {id(self.session_manager)}")

            # 保存用户消息
            session, truncate_marker = self.session_manager.save_round(
                session_id=prefixed_session_id,
                role="user",
                content=user_message,
            )
            print(
                f"[CONTEXT DEBUG] save_round user result: session={'exists' if session else 'None'}, truncate={truncate_marker}"
            )

            # 保存助手回复
            session, truncate_marker = self.session_manager.save_round(
                session_id=prefixed_session_id,
                role="assistant",
                content=assistant_message,
            )

            # 保存到文件（不依赖 session_manager）
            # session_id 格式是 "channel:sessionId"，直接用
            # trace_id 用于链路追踪，同一请求的用户消息和助手回复共享同一个trace_id
            trace_id = getattr(ctx, "trace_id", "") or ""
            print(
                f"[CONTEXT DEBUG] save_to_file called: channel={channel}, session_id={session_id}, trace_id={trace_id}",
                flush=True,
            )
            self.session_manager.save_to_file(
                channel, session_id, "user", user_message, trace_id
            )
            self.session_manager.save_to_file(
                channel, session_id, "assistant", assistant_message, trace_id
            )

            # 更新会话状态（如意图）
            intent = ctx.get("intent")
            if intent:
                state_updates = self._extract_state_updates(intent)
                if state_updates:
                    self.session_manager.update_state(
                        prefixed_session_id, state_updates
                    )

            # 触发异步数据库写入（如果有）
            if self._async_db_write:
                self._trigger_async_write(prefixed_session_id, ctx)

            # 标记会话已更新
            ctx.set("session_updated", True)
            ctx.set("session_id", prefixed_session_id)

            duration = time.time() - start_time

            return StepResult(
                success=True,
                data={
                    "session_id": prefixed_session_id,
                    "truncate_marker": truncate_marker.to_dict()
                    if truncate_marker
                    else None,
                },
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "session_id": prefixed_session_id,
                    "async_write_triggered": self._async_db_write,
                    "duration_ms": int(duration * 1000),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            print(f"[CONTEXT ERROR] {type(e).__name__}: {str(e)}", flush=True)
            return StepResult(
                success=False,
                error=f"ContextStep failed: {type(e).__name__}: {str(e)}",
                step_name=self.name,
                step_type=self.step_type.value,
                duration=duration,
                metadata={
                    "error_type": type(e).__name__,
                    "duration_ms": int(duration * 1000),
                },
            )

    def _extract_state_updates(self, intent: Any) -> Dict[str, str]:
        """
        从意图中提取状态更新

        Args:
            intent: 意图对象

        Returns:
            状态字典
        """
        state: Dict[str, str] = {}

        try:
            if hasattr(intent, "intent_type"):
                state["intent_type"] = (
                    intent.intent_type.value
                    if hasattr(intent.intent_type, "value")
                    else str(intent.intent_type)
                )

            if hasattr(intent, "query_type") and intent.query_type:
                state["query_type"] = (
                    intent.query_type.value
                    if hasattr(intent.query_type, "value")
                    else str(intent.query_type)
                )

            if hasattr(intent, "action_type") and intent.action_type:
                state["action_type"] = (
                    intent.action_type.value
                    if hasattr(intent.action_type, "value")
                    else str(intent.action_type)
                )

            if hasattr(intent, "knowledge_type"):
                state["knowledge_type"] = intent.knowledge_type

            if hasattr(intent, "reason"):
                state["reason"] = intent.reason
        except Exception:
            pass

        return state

    def _trigger_async_write(self, session_id: str, ctx: "PipelineContext"):
        """
        触发异步数据库写入

        这是一个 stub 实现，实际可以连接到真实的数据库。

        Args:
            session_id: 会话ID
            ctx: Pipeline上下文
        """

        # 在后台线程中执行异步写入
        def async_write():
            try:
                # 获取会话数据
                session = self.session_manager.get_session(session_id)
                if not session:
                    return

                # 这里可以添加真实的数据库写入逻辑
                # 例如：await db.sessions.upsert(session.to_dict())

                # 模拟异步写入
                self._pending_writes[session_id] = {
                    "status": "completed",
                    "timestamp": time.time(),
                }
            except Exception as e:
                # 记录错误但不阻塞主流程
                print(f"Async write failed for session {session_id}: {e}")

        # 启动后台线程
        thread = threading.Thread(target=async_write, daemon=True)
        thread.start()

    def get_pending_writes(self) -> Dict[str, Any]:
        """获取待处理的异步写入状态"""
        return self._pending_writes.copy()
