"""
Pytest fixtures and test setup for integration/E2E tests.

This module provides:
- Mock fixtures for external dependencies (LLM, Redis, Session)
- FastAPI TestClient fixture
- Valid JWT auth headers
- pytest-asyncio configuration
"""

import pytest
import sys
import os
import asyncio
import time
from typing import Dict, Any, Generator, AsyncGenerator
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# pytest-asyncio configuration
# =============================================================================

pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "e2e: end-to-end test")
    config.addinivalue_line("markers", "integration: integration test")


# =============================================================================
# Async event loop fixture
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Mock LLM Provider
# =============================================================================

class MockLLMProvider:
    """Mock LLM Provider for testing."""
    
    def __init__(self, response_content: str = "Mock LLM response", should_fail: bool = False):
        self._response_content = response_content
        self._should_fail = should_fail
        self.name = "mock_provider"
        self.chat_call_count = 0
        self.achat_call_count = 0
    
    @property
    def default_config(self):
        from llm.base import LLMConfig
        return LLMConfig()
    
    def chat(self, messages, config=None):
        self.chat_call_count += 1
        if self._should_fail:
            from llm.base import LLMResponse
            return LLMResponse(content="", error="Mock provider failure")
        
        from llm.base import LLMResponse
        return LLMResponse(
            content=self._response_content,
            model=self.name,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            metadata={"model_used": self.name}
        )
    
    async def achat(self, messages, config=None):
        self.achat_call_count += 1
        if self._should_fail:
            from llm.base import LLMResponse
            return LLMResponse(content="", error="Mock provider failure")
        
        from llm.base import LLMResponse
        return LLMResponse(
            content=self._response_content,
            model=self.name,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            metadata={"model_used": self.name}
        )
    
    def chat_stream(self, messages, config=None):
        """Yield response in chunks."""
        for chunk in self._response_content.split():
            yield chunk


@pytest.fixture
def mock_llm() -> Generator[MockLLMProvider, None, None]:
    """Provide a mock LLM provider that returns predictable responses."""
    provider = MockLLMProvider(response_content="Test LLM response")
    yield provider


@pytest.fixture
def mock_llm_failing() -> Generator[MockLLMProvider, None, None]:
    """Provide a mock LLM provider that always fails."""
    provider = MockLLMProvider(should_fail=True)
    yield provider


# =============================================================================
# Mock Redis
# =============================================================================

class MockRedis:
    """In-memory mock Redis for testing."""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._hits = 0
        self._misses = 0
    
    def set(self, key: str, value: Any, ex: int = 0) -> bool:
        self._data[key] = value
        if ex and ex > 0:
            self._expiry[key] = time.time() + ex
        return True
    
    def get(self, key: str) -> Any:
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                self._misses += 1
                return None
        self._hits += 1
        return self._data.get(key)
    
    def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            if key in self._expiry:
                del self._expiry[key]
            return 1
        return 0
    
    def exists(self, key: str) -> int:
        return 1 if key in self._data else 0
    
    def expire(self, key: str, seconds: int) -> bool:
        if key in self._data:
            self._expiry[key] = time.time() + seconds
            return True
        return False
    
    def ttl(self, key: str) -> int:
        if key in self._expiry:
            remaining = self._expiry[key] - time.time()
            return int(remaining) if remaining > 0 else -2
        return -2 if key not in self._data else -1
    
    def flushall(self) -> bool:
        self._data.clear()
        self._expiry.clear()
        return True
    
    def keys(self, pattern: str = "*") -> list:
        import fnmatch
        return fnmatch.filter(self._data.keys(), pattern)
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


@pytest.fixture
def mock_redis() -> Generator[MockRedis, None, None]:
    """Provide a mock Redis instance."""
    redis = MockRedis()
    yield redis
    redis.flushall()


# =============================================================================
# Mock Session Manager
# =============================================================================

class MockSessionManager:
    """Mock Session Manager for testing."""
    
    def __init__(self):
        self._sessions: Dict[str, Any] = {}
        self._save_round_called_with: list = []
        self._update_state_called_with: list = []
    
    def create_session(self, user_id: str, channel: str = "web", session_type: str = "general"):
        from session.models import SessionContext
        import uuid
        session_id = str(uuid.uuid4())
        session = SessionContext(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            expire_at="2099-12-31 23:59:59"
        )
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str):
        return self._sessions.get(session_id)
    
    def save_round(self, session_id: str, role: str, content: str):
        self._save_round_called_with.append({"session_id": session_id, "role": role, "content": content})
        session = self._sessions.get(session_id)
        return session, None
    
    def update_state(self, session_id: str, state: Dict[str, str]):
        self._update_state_called_with.append({"session_id": session_id, "state": state})
        return True
    
    def get_user_sessions(self, user_id: str) -> list:
        return [s for s in self._sessions.values() if s.user_id == user_id]
    
    @property
    def save_round_calls(self) -> list:
        return self._save_round_called_with
    
    @property
    def update_state_calls(self) -> list:
        return self._update_state_called_with
    
    def clear(self):
        self._sessions.clear()
        self._save_round_called_with.clear()
        self._update_state_called_with.clear()


@pytest.fixture
def mock_session_manager() -> Generator[MockSessionManager, None, None]:
    """Provide a mock session manager."""
    manager = MockSessionManager()
    yield manager
    manager.clear()


# =============================================================================
# Auth fixtures
# =============================================================================

@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Provide valid JWT auth headers for testing."""
    from gateway.auth import create_access_token
    token = create_access_token(user_id="test_user_123")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers() -> Dict[str, str]:
    """Provide invalid JWT auth headers for testing."""
    return {"Authorization": "Bearer invalid_token_12345"}


@pytest.fixture
def expired_auth_headers() -> Dict[str, str]:
    """Provide expired JWT auth headers for testing."""
    from datetime import timedelta
    from gateway.auth import create_access_token
    token = create_access_token(
        user_id="test_user_123",
        expires_delta=timedelta(seconds=-1)  # Already expired
    )
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# FastAPI TestClient fixture
# =============================================================================

@pytest.fixture
def test_client():
    """Provide a FastAPI TestClient for testing."""
    from fastapi.testclient import TestClient
    from gateway.fastapi_app import app
    
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_client_no_rate_limit():
    """Provide a FastAPI TestClient with rate limiting disabled for testing."""
    from fastapi.testclient import TestClient
    from gateway.fastapi_app import app
    from gateway.middleware import rate_limiter
    
    # Save original rate
    original_rate = rate_limiter.rate
    
    # Set very high rate limit for testing
    rate_limiter.rate = 10000
    
    with TestClient(app) as client:
        yield client
    
    # Restore original rate
    rate_limiter.rate = original_rate


# =============================================================================
# Pipeline context fixtures
# =============================================================================

@pytest.fixture
def pipeline_context():
    """Provide a fresh PipelineContext for testing."""
    from pipeline.orchestrator import PipelineContext
    import uuid
    return PipelineContext(
        trace_id=f"test_trace_{uuid.uuid4().hex[:8]}",
        user_id="test_user",
        request="Test request message"
    )


# =============================================================================
# Mock Agent
# =============================================================================

@pytest.fixture
def mock_agent():
    """Provide a mock Agent for testing."""
    from agent.models import Intent, IntentType, AgentOutput, ToolCall
    from unittest.mock import Mock
    
    agent = Mock()
    
    # Setup default intent
    intent = Intent(
        intent_type=IntentType.QUERY,
        confidence=0.95,
        reason="Test intent"
    )
    
    # Setup default execution plan
    plan = ToolCall(
        step=1,
        tool_name="rag",
        reason="Test plan",
        params={}
    )
    
    agent_output = AgentOutput(
        intent=intent,
        execution_plan=[plan],
        needs_clarify=False,
        clarify_question="",
        should_terminate=False,
        terminate_reason=""
    )
    
    agent.run.return_value = agent_output
    
    return agent


# =============================================================================
# Mock RAG Tool
# =============================================================================

@pytest.fixture
def mock_rag_tool():
    """Provide a mock RAG tool for testing."""
    from tools.base import ToolResult
    from unittest.mock import Mock
    
    tool = Mock()
    tool.name = "rag"
    
    tool.execute.return_value = ToolResult(
        success=True,
        data=["RAG result 1", "RAG result 2"]
    )
    
    return tool


# =============================================================================
# Mock synthesizer
# =============================================================================

@pytest.fixture
def mock_synthesizer():
    """Provide a mock OutputSynthesizer for testing."""
    from output.synthesizer import OutputSynthesizer, OutputResult, OutputFormat
    from unittest.mock import Mock
    
    synthesizer = Mock(spec=OutputSynthesizer)
    synthesizer.synthesize.return_value = OutputResult(
        content="Synthesized test response",
        format=OutputFormat.TEXT,
        source="test"
    )
    
    return synthesizer


# =============================================================================
# Rate limiter fixture
# =============================================================================

@pytest.fixture
def rate_limiter():
    """Provide a fresh RateLimiter for testing."""
    from gateway.middleware import RateLimiter
    limiter = RateLimiter(rate=100)
    yield limiter
    # Cleanup
    limiter.buckets.clear()


@pytest.fixture
def low_rate_limiter():
    """Provide a RateLimiter with very low limit for testing rate limiting."""
    from gateway.middleware import RateLimiter
    limiter = RateLimiter(rate=5)  # Only 5 requests per second
    yield limiter
    # Cleanup
    limiter.buckets.clear()


# =============================================================================
# Helper functions for tests
# =============================================================================

def create_test_token(user_id: str, expired: bool = False) -> str:
    """Helper to create a JWT token for testing."""
    from gateway.auth import create_access_token
    from datetime import timedelta
    
    if expired:
        return create_access_token(user_id, expires_delta=timedelta(seconds=-1))
    return create_access_token(user_id)


def assert_response_valid(response_data: Dict[str, Any]) -> None:
    """Helper to validate response structure."""
    assert "trace_id" in response_data
    assert "response" in response_data
    assert "sources" in response_data
    assert "metrics" in response_data


def assert_streaming_response(response_data: Dict[str, Any]) -> None:
    """Helper to validate streaming response structure."""
    assert "trace_id" in response_data
    assert "chunk" in response_data
    assert "done" in response_data
