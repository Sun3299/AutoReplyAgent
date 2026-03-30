"""
v1 Chat Endpoint

POST /v1/chat - Synchronous chat endpoint returning full response.
接收平台发来的消息，交给 Pipeline 处理。
"""

import time
import uuid
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from gateway.models import InboundRequest, OutboundResponse, Media, SenderInfo
from pipeline.orchestrator import PipelineOrchestrator


router = APIRouter(prefix="/v1", tags=["v1"])


# 全局 PipelineOrchestrator 单例
_orchestrator: Optional[PipelineOrchestrator] = None


def get_orchestrator() -> PipelineOrchestrator:
    """获取 PipelineOrchestrator 单例"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator()
        _orchestrator.register_default_steps()
    return _orchestrator


class V1ChatResponse(BaseModel):
    """v1 chat response model."""

    requestId: str = Field(..., description="对应请求的requestId")
    responseId: str = Field(..., description="响应ID")
    sessionId: str = Field(..., description="会话ID")
    content: str = Field(..., description="机器人回复")
    traceId: str = Field(..., description="Trace ID")
    sources: List[str] = Field(default_factory=list, description="来源")
    metrics: Dict[str, float] = Field(default_factory=dict, description="性能指标")


def generate_trace_id() -> str:
    """Generate a unique trace ID."""
    return f"trace_{uuid.uuid4().hex[:16]}"


def generate_response_id() -> str:
    """Generate a unique response ID."""
    return str(uuid.uuid4())


@router.post(
    "/chat",
    response_model=V1ChatResponse,
    summary="v1 Chat",
    description="Synchronous chat endpoint for platform messages",
)
async def chat(request: InboundRequest) -> V1ChatResponse:
    """
    Handle v1 chat request from platform adapters.

    POST /v1/chat

    Request:
        InboundRequest JSON 格式:
        {
            "requestId": "uuid",
            "userId": "买家ID",
            "channel": "xianyu",
            "sessionId": "会话ID",
            "content": "用户说什么",
            ...
        }

    Response:
        V1ChatResponse:
        {
            "requestId": "对应请求ID",
            "responseId": "响应ID",
            "sessionId": "会话ID",
            "content": "机器人回复",
            "traceId": "trace_id",
            "sources": ["rag"],
            "metrics": {...}
        }
    """
    trace_id = generate_trace_id()
    response_id = generate_response_id()
    start_time = time.time()

    try:
        # 获取 PipelineOrchestrator
        orchestrator = get_orchestrator()

        # 构建初始上下文
        context = {
            "channel": request.channel,
            "session_key": request.session_key,
            "is_new_session": False,  # TODO: 根据 session_key 判断
            "sender_info": request.senderInfo.dict() if request.senderInfo else {},
            "extension": request.extension,
            "media": request.media.dict() if request.media else {},
            "msg_type": request.msgType,
            "create_time": request.createTime,
        }

        # 执行 Pipeline
        result = orchestrator.execute(
            user_id=request.userId,
            request=request.content,
            trace_id=trace_id,
            context=context,
        )

        # 计算耗时
        duration_ms = (time.time() - start_time) * 1000

        return V1ChatResponse(
            requestId=request.requestId,
            responseId=response_id,
            sessionId=request.sessionId,
            content=result.get("content", "抱歉，该回答无法提供"),
            traceId=trace_id,
            sources=result.get("sources", []),
            metrics={
                **result.get("metrics", {}),
                "gateway_latency_ms": duration_ms,
            },
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        return V1ChatResponse(
            requestId=request.requestId,
            responseId=response_id,
            sessionId=request.sessionId,
            content="服务暂时不可用，请稍后重试",
            traceId=trace_id,
            sources=[],
            metrics={"gateway_latency_ms": duration_ms},
        )
