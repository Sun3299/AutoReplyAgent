"""
Prometheus Metrics 模块

定义Prometheus格式指标，使用prometheus_client库。
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Dict, Optional

# ============================================================================
# Prometheus Metrics Definitions
# ============================================================================

# 请求相关指标
REQUEST_TOTAL = Counter(
    "autoreply_request_total",
    "Total number of requests",
    ["channel", "status"]
)

REQUEST_DURATION_SECONDS = Histogram(
    "autoreply_request_duration_seconds",
    "Request latency in seconds",
    ["step", "channel"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# 步骤级别指标
STEP_DURATION_SECONDS = Histogram(
    "autoreply_step_duration_seconds",
    "Per-step latency in seconds",
    ["step_name"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
)

# LLM相关指标
LLM_REQUESTS_TOTAL = Counter(
    "autoreply_llm_requests_total",
    "Total number of LLM requests",
    ["provider", "model"]
)

# 工具调用指标
TOOL_CALLS_TOTAL = Counter(
    "autoreply_tool_calls_total",
    "Total number of tool invocations",
    ["tool_name", "success"]
)

# 会话相关指标
ACTIVE_SESSIONS = Gauge(
    "autoreply_active_sessions",
    "Number of currently active sessions"
)

# 额外Gateway指标（与gateway/fastapi_app.py保持一致）
GATEWAY_REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total request count",
    ["method", "endpoint", "status"]
)

GATEWAY_REQUEST_LATENCY_SECONDS = Histogram(
    "gateway_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

GATEWAY_ACTIVE_REQUESTS = Gauge(
    "gateway_active_requests",
    "Number of active requests"
)

RATE_LIMIT_HITS = Counter(
    "gateway_rate_limit_hits_total",
    "Total rate limit exceeded count",
    ["user_id"]
)


class PrometheusMetricsCollector:
    """
    Prometheus指标收集器

    提供方法记录各类指标，暴露/get_metrics端点返回Prometheus格式文本。
    """

    def __init__(self):
        self._active_sessions: int = 0

    # ========================================================================
    # Request Metrics
    # ========================================================================

    def record_request(self, channel: str, status: str, duration_seconds: float):
        """
        记录请求

        Args:
            channel: 请求渠道（email, slack等）
            status: 请求状态（success, error）
            duration_seconds: 请求耗时（秒）
        """
        REQUEST_TOTAL.labels(channel=channel, status=status).inc()
        REQUEST_DURATION_SECONDS.labels(step="request", channel=channel).observe(duration_seconds)

    def record_request_by_step(self, step: str, channel: str, duration_seconds: float):
        """按步骤记录请求耗时"""
        REQUEST_DURATION_SECONDS.labels(step=step, channel=channel).observe(duration_seconds)

    # ========================================================================
    # Step Metrics
    # ========================================================================

    def record_step_duration(self, step_name: str, duration_seconds: float):
        """
        记录步骤执行时长

        Args:
            step_name: 步骤名称（agent, llm_call, tool_execution等）
            duration_seconds: 执行时长（秒）
        """
        STEP_DURATION_SECONDS.labels(step_name=step_name).observe(duration_seconds)

    # ========================================================================
    # LLM Metrics
    # ========================================================================

    def record_llm_request(self, provider: str, model: str):
        """
        记录LLM调用

        Args:
            provider: LLM提供商（openai, anthropic等）
            model: 模型名称
        """
        LLM_REQUESTS_TOTAL.labels(provider=provider, model=model).inc()

    # ========================================================================
    # Tool Metrics
    # ========================================================================

    def record_tool_call(self, tool_name: str, success: bool):
        """
        记录工具调用

        Args:
            tool_name: 工具名称
            success: 是否成功
        """
        TOOL_CALLS_TOTAL.labels(
            tool_name=tool_name,
            success="true" if success else "false"
        ).inc()

    # ========================================================================
    # Session Metrics
    # ========================================================================

    def session_started(self):
        """新会话开始"""
        self._active_sessions += 1
        ACTIVE_SESSIONS.set(self._active_sessions)

    def session_ended(self):
        """会话结束"""
        self._active_sessions = max(0, self._active_sessions - 1)
        ACTIVE_SESSIONS.set(self._active_sessions)

    def get_active_sessions(self) -> int:
        """获取当前活跃会话数"""
        return self._active_sessions

    # ========================================================================
    # Gateway Metrics (delegates to module-level metrics)
    # ========================================================================

    def record_gateway_request(self, method: str, endpoint: str, status: int):
        """记录Gateway请求"""
        GATEWAY_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status=str(status)
        ).inc()

    def record_gateway_latency(self, method: str, endpoint: str, duration_seconds: float):
        """记录Gateway延迟"""
        GATEWAY_REQUEST_LATENCY_SECONDS.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration_seconds)

    def increment_active_requests(self):
        """增加活跃请求数"""
        GATEWAY_ACTIVE_REQUESTS.inc()

    def decrement_active_requests(self):
        """减少活跃请求数"""
        GATEWAY_ACTIVE_REQUESTS.dec()

    def record_rate_limit_hit(self, user_id: str):
        """记录限流触发"""
        RATE_LIMIT_HITS.labels(user_id=user_id).inc()


_metrics_collector: Optional[PrometheusMetricsCollector] = None


def get_metrics_collector() -> PrometheusMetricsCollector:
    """获取全局指标收集器实例"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = PrometheusMetricsCollector()
    return _metrics_collector


def get_metrics() -> bytes:
    """
    获取Prometheus格式的指标数据

    用于/metrics端点返回。

    Returns:
        bytes: Prometheus格式的指标文本
    """
    return generate_latest()


def get_content_type() -> str:
    """获取Prometheus内容的Content-Type"""
    return CONTENT_TYPE_LATEST
