"""
FastAPI API Gateway Application

Provides HTTP interface with rate limiting, authentication, and v1/v2 routing.
"""

import time
import threading
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from gateway.routes import v1_router, v2_router
from gateway.middleware import rate_limiter
from gateway.auth import create_access_token
from observability.prometheus_metrics import (
    GATEWAY_REQUESTS_TOTAL,
    GATEWAY_REQUEST_LATENCY_SECONDS,
    GATEWAY_ACTIVE_REQUESTS,
    RATE_LIMIT_HITS,
)


# Aliases for backward compatibility
REQUEST_COUNT = GATEWAY_REQUESTS_TOTAL
REQUEST_LATENCY = GATEWAY_REQUEST_LATENCY_SECONDS
ACTIVE_REQUESTS = GATEWAY_ACTIVE_REQUESTS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    print("Starting API Gateway...")
    yield
    # Shutdown
    print("Shutting down API Gateway...")


# Create FastAPI application
app = FastAPI(
    title="AutoReply API Gateway",
    description="API Gateway with JWT authentication, rate limiting, and v1/v2 routing",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics."""
    start_time = time.time()
    
    # Track active requests
    ACTIVE_REQUESTS.inc()
    
    try:
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        endpoint = request.url.path
        method = request.method
        status_code = response.status_code
        
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
        
        return response
    finally:
        ACTIVE_REQUESTS.dec()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent JSON format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code
        },
        headers=exc.headers if hasattr(exc, "headers") else {}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    # Log error but don't expose internal details
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal server error",
            "status_code": 500
        }
    )


# Include routers
app.include_router(v1_router)
app.include_router(v2_router)


@app.get(
    "/health",
    summary="Health Check",
    description="Check if the gateway is healthy",
    tags=["health"]
)
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.
    
    GET /health
    
    Returns:
        200: {"status": "healthy", "timestamp": "...", "rate_limiter": {...}}
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "rate_limiter": {
            "active_users": len(rate_limiter.buckets),
            "rate_limit": rate_limiter.rate
        }
    }


@app.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Expose Prometheus metrics for monitoring",
    tags=["monitoring"]
)
async def metrics():
    """
    Prometheus metrics endpoint.
    
    GET /metrics
    
    Returns:
        200: Prometheus-formatted metrics text
    """
    # Cleanup inactive buckets periodically
    rate_limiter.cleanup_inactive_buckets(max_idle_seconds=3600)
    
    from observability.prometheus_metrics import get_metrics, get_content_type
    
    return Response(
        content=get_metrics(),
        media_type=get_content_type()
    )


def _parse_prometheus_metrics() -> Dict[str, Any]:
    """Parse Prometheus metrics into a dictionary."""
    metrics_output = generate_latest().decode("utf-8")
    
    result = {}
    for line in metrics_output.split("\n"):
        if line and not line.startswith("#") and "{" not in line:
            parts = line.split()
            if len(parts) >= 2:
                metric_name = parts[0]
                try:
                    metric_value = float(parts[1])
                    result[metric_name] = metric_value
                except ValueError:
                    pass
    
    return result


@app.post(
    "/token",
    summary="Create Test Token",
    description="Create a test JWT token (for development only)",
    tags=["auth"]
)
async def create_token(user_id: str) -> Dict[str, Any]:
    """
    Create a test JWT token for development purposes.
    
    POST /token
    
    Args:
        user_id: User identifier to encode in token
        
    Returns:
        200: {"access_token": "...", "token_type": "bearer", "expires_in": ...}
    """
    token = create_access_token(user_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600
    }


@app.get(
    "/",
    summary="Root",
    description="Gateway root endpoint",
    tags=["root"]
)
async def root():
    """Root endpoint with gateway info."""
    return {
        "name": "AutoReply API Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
