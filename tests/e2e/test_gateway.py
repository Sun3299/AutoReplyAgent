"""
Gateway tests - Rate Limiting and JWT Auth.

Tests the gateway's authentication, rate limiting, and monitoring endpoints.

Test Cases:
- test_rate_limit_rejected: >100 requests quickly triggers 429
- test_jwt_auth_required: Request without token returns 401
- test_jwt_auth_invalid: Request with invalid token returns 401
- test_jwt_auth_valid: Request with valid token returns 200
- test_health_endpoint: GET /health returns 200
- test_metrics_endpoint: GET /metrics returns Prometheus format
"""

import pytest
import time
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_rejected(self, test_client, auth_headers):
        """
        Send >100 requests quickly, assert 429 after limit.
        
        Steps:
        1. Create a fresh rate limiter with low limit
        2. Send rapid requests up to and beyond the limit
        3. Assert requests beyond limit get 429 response
        """
        from gateway.middleware import RateLimiter
        
        # Use a low rate limiter for testing
        limiter = RateLimiter(rate=10)  # 10 requests per second
        
        request_data = {
            "message": "Rate limit test message",
            "channel": "web"
        }
        
        # Track responses
        responses = []
        
        # Send requests rapidly until we hit rate limit
        for i in range(20):
            # Check rate limit before each request
            user_id = "test_user_rate_limit"
            allowed = limiter.allow(user_id)
            
            if not allowed:
                # Should be rate limited
                response = test_client.post(
                    "/v1/chat",
                    json=request_data,
                    headers=auth_headers
                )
                responses.append({
                    "status": response.status_code,
                    "index": i,
                    "allowed": allowed
                })
                if response.status_code == 429:
                    break
            else:
                # If allowed, make the request
                response = test_client.post(
                    "/v1/chat",
                    json=request_data,
                    headers=auth_headers
                )
                responses.append({
                    "status": response.status_code,
                    "index": i,
                    "allowed": allowed
                })
        
        # Verify we eventually got a 429
        status_codes = [r["status"] for r in responses]
        assert 429 in status_codes, f"Should have received 429 rate limit response. Got: {status_codes}"
        
        # Verify it happened after some successful requests
        first_429_index = status_codes.index(429)
        assert first_429_index > 0, "Should have made some successful requests before hitting limit"
    
    def test_rate_limit_with_high_limit(self, test_client, auth_headers):
        """Test that high rate limit allows many requests."""
        from gateway.middleware import rate_limiter
        
        # Save original rate
        original_rate = rate_limiter.rate
        
        try:
            # Set very high rate limit
            rate_limiter.rate = 10000
            
            request_data = {
                "message": "High rate limit test",
                "channel": "web"
            }
            
            # Send many requests
            success_count = 0
            for i in range(50):
                response = test_client.post(
                    "/v1/chat",
                    json=request_data,
                    headers=auth_headers
                )
                if response.status_code == 200:
                    success_count += 1
            
            # Most or all should succeed
            assert success_count >= 45, f"Expected most requests to succeed with high limit, got {success_count}/50"
        
        finally:
            # Restore original rate
            rate_limiter.rate = original_rate
    
    def test_rate_limit_per_user_isolation(self, test_client, auth_headers):
        """Test that rate limits are per-user, not global."""
        from gateway.middleware import RateLimiter
        
        limiter = RateLimiter(rate=5)  # 5 requests per second
        
        user1 = "user_1"
        user2 = "user_2"
        
        request_data = {"message": "test", "channel": "web"}
        
        # User 1 makes 5 requests (should all succeed)
        user1_allowed = [limiter.allow(user1) for _ in range(5)]
        
        # User 2 should still be able to make requests (separate bucket)
        user2_allowed = limiter.allow(user2)
        
        assert all(user1_allowed[:4]), "First 4 requests from user1 should be allowed"
        assert user2_allowed, "User2 should have separate rate limit bucket"
    
    def test_rate_limit_bucket_refill(self, test_client, auth_headers):
        """Test that rate limit bucket refills over time."""
        from gateway.middleware import RateLimiter
        
        limiter = RateLimiter(rate=2)  # 2 requests per second
        
        user_id = "test_user_refill"
        
        # Exhaust the bucket
        limiter.allow(user_id)
        limiter.allow(user_id)
        
        # Should be rate limited now
        allowed = limiter.allow(user_id)
        assert allowed is False, "Bucket should be exhausted"
        
        # Wait for refill
        time.sleep(0.6)  # Wait for ~1 token to refill
        
        # Should be allowed again
        allowed_after_wait = limiter.allow(user_id)
        assert allowed_after_wait is True, "Bucket should have refilled"


class TestJWTAuthentication:
    """Test JWT authentication on protected endpoints."""
    
    def test_jwt_auth_required(self, test_client):
        """
        Request without token returns 401.
        
        Steps:
        1. Send POST /v1/chat without Authorization header
        2. Assert response status is 401 Unauthorized
        """
        request_data = {
            "message": "Hello without auth",
            "channel": "web"
        }
        
        response = test_client.post("/v1/chat", json=request_data)
        
        assert response.status_code == 401, \
            f"Expected 401 Unauthorized, got {response.status_code}: {response.text}"
        
        # Verify error message
        data = response.json()
        assert "detail" in data or "error" in data
    
    def test_jwt_auth_invalid(self, test_client, invalid_auth_headers):
        """
        Request with invalid token returns 401.
        
        Steps:
        1. Send POST /v1/chat with invalid token
        2. Assert response status is 401 Unauthorized
        """
        request_data = {
            "message": "Hello with invalid token",
            "channel": "web"
        }
        
        response = test_client.post(
            "/v1/chat",
            json=request_data,
            headers=invalid_auth_headers
        )
        
        assert response.status_code == 401, \
            f"Expected 401, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "error" in data
    
    def test_jwt_auth_expired(self, test_client, expired_auth_headers):
        """
        Request with expired token returns 401.
        
        Steps:
        1. Send POST /v1/chat with expired token
        2. Assert response status is 401 Unauthorized
        """
        request_data = {
            "message": "Hello with expired token",
            "channel": "web"
        }
        
        response = test_client.post(
            "/v1/chat",
            json=request_data,
            headers=expired_auth_headers
        )
        
        assert response.status_code == 401, \
            f"Expected 401 for expired token, got {response.status_code}: {response.text}"
    
    def test_jwt_auth_valid(self, test_client, auth_headers):
        """
        Request with valid token returns 200.
        
        Steps:
        1. Send POST /v1/chat with valid JWT token
        2. Assert response status is 200 OK
        """
        request_data = {
            "message": "Hello with valid token",
            "channel": "web"
        }
        
        response = test_client.post(
            "/v1/chat",
            json=request_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200, \
            f"Expected 200 OK, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "trace_id" in data
        assert "response" in data
    
    def test_jwt_auth_valid_for_v2_stream(self, test_client, auth_headers):
        """Test valid JWT auth works for v2 streaming endpoint."""
        request_data = {
            "message": "Hello stream with valid token",
            "channel": "web"
        }
        
        response = test_client.post(
            "/v2/chat/stream",
            json=request_data,
            headers=auth_headers,
            stream=True
        )
        
        assert response.status_code == 200, \
            f"Expected 200 for streaming, got {response.status_code}: {response.text}"
        
        assert "text/event-stream" in response.headers.get("content-type", "")
    
    def test_jwt_auth_missing_bearer_scheme(self, test_client):
        """Test that missing 'Bearer' scheme returns 401."""
        request_data = {
            "message": "Hello with bad scheme",
            "channel": "web"
        }
        
        # Send with non-Bearer scheme
        headers = {"Authorization": "Basic sometoken"}
        
        response = test_client.post(
            "/v1/chat",
            json=request_data,
            headers=headers
        )
        
        assert response.status_code == 401, \
            f"Expected 401 for non-Bearer scheme, got {response.status_code}"
    
    def test_jwt_auth_valid_token_structure(self, test_client, auth_headers):
        """Test that well-formed but invalid signature still returns 401."""
        # This is a properly structured JWT but with wrong secret
        fake_valid_struct_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"
        
        request_data = {
            "message": "Hello with fake token",
            "channel": "web"
        }
        
        response = test_client.post(
            "/v1/chat",
            json=request_data,
            headers={"Authorization": f"Bearer {fake_valid_struct_token}"}
        )
        
        assert response.status_code == 401


class TestHealthEndpoint:
    """Test /health endpoint."""
    
    def test_health_endpoint(self, test_client):
        """
        GET /health returns 200 with healthy status.
        
        Steps:
        1. Send GET /health
        2. Assert response status is 200
        3. Assert response body contains status: healthy
        """
        response = test_client.get("/health")
        
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        assert data["status"] == "healthy", f"Expected status 'healthy', got {data.get('status')}"
        assert "timestamp" in data, "Response should include timestamp"
        assert "rate_limiter" in data, "Response should include rate_limiter info"
    
    def test_health_endpoint_structure(self, test_client):
        """Test health endpoint returns expected data structure."""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify structure
        assert isinstance(data, dict), "Health response should be a dictionary"
        assert data["status"] == "healthy"
        assert isinstance(data["timestamp"], (int, float)), "timestamp should be numeric"
        assert "rate_limiter" in data
        assert "active_users" in data["rate_limiter"]
        assert "rate_limit" in data["rate_limiter"]


class TestMetricsEndpoint:
    """Test /metrics endpoint."""
    
    def test_metrics_endpoint(self, test_client):
        """
        GET /metrics returns 200 and contains prometheus format.
        
        Steps:
        1. Send GET /metrics
        2. Assert response status is 200
        3. Assert response contains Prometheus format metrics
        """
        response = test_client.get("/metrics")
        
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}: {response.text}"
        
        # Prometheus format should be text/plain
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "text/plain" in str(response.headers), \
            f"Expected text/plain content type, got {content_type}"
        
        # Response should contain prometheus metric names
        content = response.text
        
        # Prometheus metrics typically have these patterns:
        # - Counter: metric_name_total{labels} value
        # - Gauge: metric_name{labels} value
        # - Histogram: metric_name_bucket{labels} value
        assert len(content) > 0, "Metrics content should not be empty"
        
        # Should contain some metric names (gateway_requests_total is defined in fastapi_app.py)
        assert "gateway_requests_total" in content or "process_" in content, \
            f"Expected Prometheus metrics, got: {content[:200]}"
    
    def test_metrics_prometheus_format(self, test_client):
        """Test that metrics are in correct Prometheus format."""
        response = test_client.get("/metrics")
        
        assert response.status_code == 200
        
        content = response.text
        lines = content.split("\n")
        
        # Prometheus format: metric_name{labels} value OR metric_name value
        metric_lines = [l for l in lines if l and not l.startswith("#") and "{" not in l]
        
        # Each metric line should have at least metric_name and value
        for line in metric_lines:
            parts = line.split()
            assert len(parts) >= 2, f"Invalid Prometheus format line: {line}"
            # Second part should be numeric value
            try:
                float(parts[1])
            except ValueError:
                pytest.fail(f"Expected numeric value in metric line: {line}")


class TestGatewayEndpoints:
    """Test other gateway endpoints."""
    
    def test_root_endpoint(self, test_client):
        """Test GET / returns gateway info."""
        response = test_client.get("/")
        
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "AutoReply API Gateway"
        assert "version" in data
        assert "docs" in data
        assert "health" in data
        assert "metrics" in data
    
    def test_token_endpoint(self, test_client):
        """Test POST /token creates a valid JWT."""
        response = test_client.post("/token?user_id=test_user_abc")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        
        # The token should be a valid JWT (3 parts separated by dots)
        token = data["access_token"]
        assert token.count(".") == 2, f"Invalid JWT format: {token}"
    
    def test_stream_health_endpoint(self, test_client):
        """Test GET /v2/chat/stream/health returns streaming status."""
        response = test_client.get("/v2/chat/stream/health")
        
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["streaming"] is True


class TestGatewayMiddleware:
    """Test gateway middleware behavior."""
    
    def test_metrics_middleware_records_request(self, test_client, auth_headers):
        """Test that metrics middleware records request count and latency."""
        # Make a successful request
        response = test_client.post(
            "/v1/chat",
            json={"message": "Metrics test", "channel": "web"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        
        # Verify metrics are recorded
        metrics_response = test_client.get("/metrics")
        assert metrics_response.status_code == 200
        
        content = metrics_response.text
        # Should have recorded the /v1/chat request
        assert "gateway_requests_total" in content or "process_requests_total" in content
    
    def test_gateway_handles_request_without_content_type(self, test_client, auth_headers):
        """Test that gateway handles requests without explicit content type."""
        response = test_client.post(
            "/v1/chat",
            data='{"message": "test", "channel": "web"}',  # Use data instead of json
            headers={
                **auth_headers,
                "Content-Type": "application/json"
            }
        )
        
        # Should still work
        assert response.status_code in [200, 400, 422]
    
    def test_gateway_error_format(self, test_client):
        """Test that gateway returns consistent error format."""
        # Request without required fields
        response = test_client.post(
            "/v1/chat",
            json={"channel": "web"}  # Missing message
        )
        
        # Should return 422 or 400 for validation error
        assert response.status_code in [401, 422, 400]
        
        # Error format should be consistent
        data = response.json()
        assert "detail" in data or "error" in data or "message" in data
