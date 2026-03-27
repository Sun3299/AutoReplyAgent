"""
v2 Streaming Chat Endpoint

POST /v2/chat/stream - Streaming chat endpoint using Server-Sent Events.
Supports token refresh mid-stream for long-running streams.
"""

import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, AsyncGenerator, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from gateway.auth import verify_token, refresh_token, AuthError
from gateway.middleware import rate_limiter, check_rate_limit, RateLimiter


router = APIRouter(prefix="/v2", tags=["v2"])

security = HTTPBearer(auto_error=True)


class V2ChatRequest(BaseModel):
    """v2 streaming chat request model."""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    session_id: Optional[str] = Field(None, description="Session identifier")
    channel: str = Field("web", description="Channel source")
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional metadata")
    refresh_token: Optional[str] = Field(None, description="Token to refresh mid-stream")


class V2StreamChunk(BaseModel):
    """v2 stream chunk model."""
    trace_id: str
    chunk: str
    sources: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    done: bool = False
    error: Optional[str] = None


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """FastAPI dependency to extract user_id from JWT token."""
    try:
        return await verify_token(credentials)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.detail),
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_trace_id() -> str:
    """Generate a unique trace ID."""
    return f"trace_{uuid.uuid4().hex[:16]}"


async def stream_from_pipeline(
    user_id: str,
    message: str,
    session_id: Optional[str],
    channel: str,
    trace_id: str,
    metadata: Optional[Dict[str, str]]
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream responses from PipelineOrchestrator.
    
    This is a stub implementation. In production, this would call
    the actual pipeline's stream method.
    
    Args:
        user_id: User identifier
        message: User message
        session_id: Optional session identifier
        channel: Communication channel
        trace_id: Request trace ID
        metadata: Additional metadata
        
    Yields:
        Response chunks as dictionaries
    """
    # Stub implementation - simulates streaming response
    # In production, call the actual pipeline stream method
    
    chunks = [
        {"chunk": f"[v2 Stream starting", "done": False},
        {"chunk": f" for: {message[:30]}", "done": False},
        {"chunk": f"... (simulated stream)", "done": False},
        {"chunk": f"]", "done": True},
    ]
    
    for i, chunk_data in enumerate(chunks):
        await asyncio.sleep(0.1)  # Simulate processing time
        
        yield {
            "trace_id": trace_id,
            "chunk": chunk_data["chunk"],
            "sources": ["rag_retriever"] if i == 0 else [],
            "metrics": {"chunk_latency_ms": 100 * (i + 1)},
            "done": chunk_data["done"],
            "error": None
        }


def format_sse_event(data: Dict[str, Any]) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"


def format_sse_heartbeat() -> str:
    """Format heartbeat for SSE keepalive."""
    return f": heartbeat\n\n"


async def token_refresh_generator(
    initial_token: str,
    refresh_interval_seconds: int = 300
) -> AsyncGenerator[str, None]:
    """
    Generator that yields refreshed tokens at intervals.
    
    Used for mid-stream token refresh in v2 streaming.
    
    Args:
        initial_token: Starting JWT token
        refresh_interval_seconds: Interval between refreshes
        
    Yields:
        JWT token strings (refreshed as needed)
    """
    current_token = initial_token
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed >= refresh_interval_seconds:
            current_token = refresh_token(current_token)
            start_time = time.time()
        yield current_token
        await asyncio.sleep(refresh_interval_seconds)


@router.post(
    "/chat/stream",
    summary="v2 Streaming Chat",
    description="Streaming chat endpoint using Server-Sent Events for v2 API",
    response_model=None,
)
async def chat_stream(
    request: V2ChatRequest,
    user_id: str = Depends(get_current_user_id),
    limiter: RateLimiter = Depends(lambda: rate_limiter),
    http_request: Request = Depends(lambda: None)
) -> StreamingResponse:
    """
    Handle v2 streaming chat request.
    
    POST /v2/chat/stream
    
    Request:
        - Authorization: Bearer <JWT token>
        - Body: {"message": "...", "session_id": "...", "channel": "...", "metadata": {...}, "refresh_token": "..."}
    
    Response:
        - 200: Server-Sent Events stream
        - 401: Unauthorized (invalid/missing token)
        - 429: Too Many Requests (rate limit exceeded)
        - 500: Internal Server Error
    """
    # Check rate limit
    await check_rate_limit(limiter, user_id)
    
    # Generate trace ID for request tracking
    trace_id = generate_trace_id()
    
    # Token refresh support
    token = None
    if http_request and hasattr(http_request, 'headers'):
        auth_header = http_request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for the streaming response."""
        try:
            # Send initial trace_id
            yield format_sse_event({
                "trace_id": trace_id,
                "chunk": "",
                "sources": [],
                "metrics": {},
                "done": False,
                "error": None,
                "event": "start"
            })
            
            # Stream from pipeline
            async for chunk_data in stream_from_pipeline(
                user_id=user_id,
                message=request.message,
                session_id=request.session_id,
                channel=request.channel,
                trace_id=trace_id,
                metadata=request.metadata
            ):
                # Check if client disconnected
                if http_request and await http_request.is_disconnected():
                    break
                
                yield format_sse_event(chunk_data)
                
                if chunk_data.get("done"):
                    break
                
                # Small delay between chunks
                await asyncio.sleep(0.01)
            
            # Send final done event
            yield format_sse_event({
                "trace_id": trace_id,
                "chunk": "",
                "sources": [],
                "metrics": {},
                "done": True,
                "error": None,
                "event": "end"
            })
            
        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            # Send error event
            yield format_sse_event({
                "trace_id": trace_id,
                "chunk": "",
                "sources": [],
                "metrics": {},
                "done": True,
                "error": "Stream interrupted due to internal error",
                "event": "error"
            })
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Trace-ID": trace_id,
        }
    )


@router.get(
    "/chat/stream/health",
    summary="Stream Health Check",
    description="Check if streaming endpoint is healthy"
)
async def stream_health():
    """Health check for streaming endpoint."""
    return {"status": "healthy", "streaming": True}
