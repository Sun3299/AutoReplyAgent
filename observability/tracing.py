"""
TracingManager 链路追踪管理器

OpenTelemetry风格的追踪集成，增强pipeline/trace.py中的TraceManager。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
import uuid


@dataclass
class TraceSpan:
    """追踪节点"""
    trace_id: str
    span_id: str
    step_name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""

    def finish(self, success: bool = True, error: str = ""):
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.success = success
        self.error = error


@dataclass
class RequestTrace:
    """完整请求追踪"""
    trace_id: str
    user_id: str = ""
    request: str = ""
    response: str = ""
    status: str = "success"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    spans: List[TraceSpan] = field(default_factory=list)

    def add_span(self, span: TraceSpan):
        self.spans.append(span)

    def finish(self, status: str = "success"):
        self.end_time = datetime.now()
        self.status = status

    def total_duration_ms(self) -> float:
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0


class TracingManager:
    """
    链路追踪管理器

    存储内存中的追踪记录，支持按trace_id检索。
    提供OpenTelemetry风格的接口。

    使用示例：
        tm = TracingManager()

        # 开始请求
        tm.start_request("req-123", user_id="user1", request="查询订单")

        # 记录步骤
        tm.record_step_duration("req-123", "agent", 5.2)
        tm.record_step_duration("req-123", "llm_call", 120.5)

        # 结束请求
        tm.end_request("req-123", response="订单详情")

        # 获取追踪
        trace = tm.get_trace("req-123")
    """

    def __init__(self):
        self._traces: Dict[str, RequestTrace] = {}
        self._current_span: Optional[TraceSpan] = None

    def start_request(
        self,
        trace_id: Optional[str] = None,
        user_id: str = "",
        request: str = "",
    ) -> str:
        """
        开始一个请求追踪

        Args:
            trace_id: 追踪ID，默认自动生成
            user_id: 用户ID
            request: 请求内容

        Returns:
            trace_id: 追踪ID
        """
        tid = trace_id or str(uuid.uuid4())
        trace = RequestTrace(
            trace_id=tid,
            user_id=user_id,
            request=request,
        )
        self._traces[tid] = trace
        return tid

    def end_request(
        self,
        trace_id: str,
        response: str = "",
        status: str = "success",
        error: str = "",
    ) -> Optional[RequestTrace]:
        """
        结束请求追踪

        Args:
            trace_id: 追踪ID
            response: 响应内容
            status: 状态 success/error
            error: 错误信息

        Returns:
            RequestTrace: 追踪记录
        """
        trace = self._traces.get(trace_id)
        if not trace:
            return None

        trace.response = response
        if error:
            trace.status = "error"
            # 添加错误作为最后一个span
            error_span = TraceSpan(
                trace_id=trace_id,
                span_id=str(uuid.uuid4()),
                step_name="error",
                success=False,
                error=error,
            )
            error_span.finish(success=False, error=error)
            trace.add_span(error_span)
        else:
            trace.status = status
        trace.finish(status=trace.status)
        return trace

    def record_step_duration(
        self,
        trace_id: str,
        step_name: str,
        duration_ms: float,
        success: bool = True,
        error: str = "",
    ) -> Optional[TraceSpan]:
        """
        记录步骤执行时长

        Args:
            trace_id: 追踪ID
            step_name: 步骤名称
            duration_ms: 执行时长（毫秒）
            success: 是否成功
            error: 错误信息

        Returns:
            TraceSpan: 追踪节点
        """
        trace = self._traces.get(trace_id)
        if not trace:
            return None

        span = TraceSpan(
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
            step_name=step_name,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        # 计算start_time和end_time基于duration
        from datetime import timedelta
        span.end_time = trace.start_time + timedelta(milliseconds=duration_ms)
        # 估算start_time（基于之前span的总时长）
        prev_duration = sum(s.duration_ms for s in trace.spans)
        span.start_time = trace.start_time + timedelta(milliseconds=prev_duration)

        trace.add_span(span)
        return span

    def get_trace(self, trace_id: str) -> Optional[RequestTrace]:
        """
        获取追踪记录

        Args:
            trace_id: 追踪ID

        Returns:
            RequestTrace: 追踪记录，不存在返回None
        """
        return self._traces.get(trace_id)

    def get_all_traces(self) -> List[RequestTrace]:
        """获取所有追踪记录"""
        return list(self._traces.values())

    def log_trace(self, trace_id: str) -> None:
        """
        打印追踪日志（用于调试）

        Log format: trace_id=xxx step=agent duration_ms=5.2 success=true
        """
        trace = self._traces.get(trace_id)
        if not trace:
            return

        for span in trace.spans:
            print(
                f"trace_id={span.trace_id} "
                f"step={span.step_name} "
                f"duration_ms={span.duration_ms:.1f} "
                f"success={span.success}"
            )

    def record_exception(
        self,
        trace_id: str,
        step_name: str,
        exception: Exception,
    ) -> Optional[TraceSpan]:
        """
        记录异常为错误span

        Args:
            trace_id: 追踪ID
            step_name: 步骤名称
            exception: 异常对象

        Returns:
            TraceSpan: 错误节点
        """
        return self.record_step_duration(
            trace_id=trace_id,
            step_name=step_name,
            duration_ms=0.0,
            success=False,
            error=str(exception),
        )


_tracing_manager: Optional[TracingManager] = None


def get_tracing_manager() -> TracingManager:
    """获取全局追踪管理器实例"""
    global _tracing_manager
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    return _tracing_manager
