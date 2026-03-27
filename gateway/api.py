"""
API网关

提供HTTP接口，限流、鉴权、路由。
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
import time
import hashlib


class RateLimitType(Enum):
    """限流类型"""
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"


@dataclass
class GatewayConfig:
    """网关配置"""
    rate_limit: int = 100              # QPS
    rate_limit_type: RateLimitType = RateLimitType.TOKEN_BUCKET
    auth_required: bool = True
    timeout: int = 30


@dataclass
class ChatRequest:
    """聊天请求"""
    user_id: str
    message: str
    session_id: Optional[str] = None
    channel: str = "web"
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChatResponse:
    """聊天响应"""
    trace_id: str
    response: str
    sources: List[str]
    metrics: Dict[str, float]
    error: Optional[str] = None


class RateLimiter:
    """限流器（Token Bucket）"""
    
    def __init__(self, rate: int):
        self.rate = rate
        self.tokens = rate
        self.last_update = time.time()
    
    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
        self.last_update = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class Auth:
    """鉴权（简化版）"""
    
    def __init__(self):
        self.valid_tokens = set()
    
    def validate(self, token: str) -> bool:
        if not token:
            return False
        return token in self.valid_tokens or token == "dev_token"
    
    def generate_token(self, user_id: str) -> str:
        token = hashlib.sha256(f"{user_id}{time.time()}".encode()).hexdigest()[:16]
        self.valid_tokens.add(token)
        return token


class Router:
    """路由（简化版）"""
    
    def route(self, request: ChatRequest) -> Dict[str, Any]:
        return {
            "version": "v1",
            "endpoint": "/chat",
        }


class Metrics:
    """监控指标"""
    
    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.total_duration = 0.0
    
    def record(self, duration: float, error: bool = False):
        self.requests += 1
        self.total_duration += duration
        if error:
            self.errors += 1
    
    def stats(self) -> Dict[str, Any]:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "avg_duration": self.total_duration / max(1, self.requests),
            "error_rate": self.errors / max(1, self.requests),
        }


# 全局实例
_rate_limiter = RateLimiter(100)  # 100QPS
_auth = Auth()
_router = Router()
_metrics = Metrics()


def check_rate_limit() -> bool:
    """检查限流"""
    return _rate_limiter.allow()


def check_auth(token: str) -> bool:
    """检查鉴权"""
    return _auth.validate(token)


def api(request: ChatRequest, token: str = "") -> ChatResponse:
    """
    API入口
    
    Args:
        request: 聊天请求
        token: 认证token
        
    Returns:
        ChatResponse
    """
    start = time.time()
    
    # 1. 限流检查
    if not check_rate_limit():
        duration = time.time() - start
        _metrics.record(duration, error=True)
        return ChatResponse(
            trace_id="",
            response="",
            sources=[],
            metrics={},
            error="429 Too Many Requests"
        )
    
    # 2. 鉴权检查
    if not check_auth(token):
        duration = time.time() - start
        _metrics.record(duration, error=True)
        return ChatResponse(
            trace_id="",
            response="",
            sources=[],
            metrics={},
            error="401 Unauthorized"
        )
    
    # 3. 路由
    route = _router.route(request)
    
    # 4. 调用Pipeline（实际应该在pipeline模块，这里简化）
    # from pipeline import PipelineOrchestrator
    # result = orchestrator.execute(request.user_id, request.message)
    
    duration = time.time() - start
    _metrics.record(duration)
    
    return ChatResponse(
        trace_id=f"trace_{int(time.time())}",
        response="[Pipeline响应占位]",
        sources=["rag", "external"],
        metrics={"total": duration}
    )


def get_metrics() -> Dict[str, Any]:
    """获取监控指标"""
    return _metrics.stats()
