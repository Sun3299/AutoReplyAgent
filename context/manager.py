"""
context/manager.py - Session context manager

Manages session, cache, and persistence layers.
Integrates SessionHandler for full-featured session management.

Updated to use:
- RedisCache for session state caching
- AsyncDBWriter for async database persistence
- SessionHandler for integrated session management
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .cache import RedisCache
from .async_db import AsyncDBWriter
from .session_handler import SessionHandler


class MessageRole:
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """消息"""
    role: str
    content: str
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class SessionContext:
    """会话上下文"""
    session_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    expired_at: str = ""
    trace_id: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.expired_at:
            self.expired_at = (datetime.now() + timedelta(hours=24)).isoformat()
        if not self.trace_id:
            self.trace_id = str(uuid.uuid4())
    
    def is_expired(self) -> bool:
        return datetime.now() > datetime.fromisoformat(self.expired_at)
    
    def add_message(self, role: str, content: str):
        self.messages.append(Message(role=role, content=content))
        self.updated_at = datetime.now().isoformat()
    
    def get_messages(self, limit: int = 10) -> List[Message]:
        return self.messages[-limit:]
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": [m.to_dict() for m in self.messages],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expired_at": self.expired_at,
            "trace_id": self.trace_id,
        }


class ContextManager:
    """
    Session context manager with cache and persistence.
    
    Provides session creation, storage, and querying.
    Integrates with SessionHandler for full session management.
    
    Attributes:
        session_handler: SessionHandler instance for session operations
        default_ttl: Default TTL in hours
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        db_url: Optional[str] = None,
        default_ttl: int = 24,
    ):
        """
        Initialize ContextManager.
        
        Args:
            redis_url: Redis connection URL (optional)
            db_url: Database connection URL (optional)
            default_ttl: Default TTL in hours
        """
        self.default_ttl = default_ttl
        
        # Initialize components with graceful degradation
        self._cache: Optional[RedisCache] = None
        self._db_writer: Optional[AsyncDBWriter] = None
        self._session_handler: Optional[SessionHandler] = None
        
        # Try to initialize Redis cache
        try:
            self._cache = RedisCache(redis_url=redis_url)
        except Exception:
            pass
        
        # Try to initialize async DB writer
        try:
            self._db_writer = AsyncDBWriter(db_url=db_url)
        except Exception:
            pass
        
        # Initialize session handler with cache and DB writer
        if self._cache or self._db_writer:
            self._session_handler = SessionHandler(
                cache=self._cache,
                db_writer=self._db_writer,
            )
        
        # Legacy in-memory storage for backwards compatibility
        self.storage: Dict[str, SessionContext] = {}
    
    @property
    def trace_id(self) -> str:
        """Generate a new trace ID for logging."""
        return str(uuid.uuid4())
    
    def create(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        channel: str = "web",
        session_type: str = "general",
    ) -> SessionContext:
        """
        Create a new session.
        
        Args:
            user_id: User ID
            session_id: Optional session ID
            metadata: Optional metadata dict
            channel: Source channel
            session_type: Session type
            
        Returns:
            SessionContext
        """
        # Generate trace_id for the session
        trace_id = str(uuid.uuid4())
        
        session = SessionContext(
            session_id=session_id or str(uuid.uuid4()),
            user_id=user_id,
            metadata=metadata or {},
            trace_id=trace_id,
        )
        
        self.storage[session.session_id] = session
        
        # Also create via SessionHandler if available
        if self._session_handler:
            self._session_handler.create_session(
                user_id=user_id,
                channel=channel,
                session_type=session_type,
            )
        
        return session
    
    def get(self, session_id: str) -> Optional[SessionContext]:
        """
        Get session by ID.
        
        Checks SessionHandler cache first, then falls back to storage.
        """
        # Try SessionHandler first
        if self._session_handler:
            cached = self._session_handler.get_session(session_id)
            if cached:
                # Return as SessionContext for backwards compatibility
                return self._dict_to_session_context(cached)
        
        # Fall back to storage
        session = self.storage.get(session_id)
        if session and session.is_expired():
            del self.storage[session_id]
            return None
        return session
    
    def _dict_to_session_context(self, data: Dict[str, Any]) -> SessionContext:
        """Convert dict to SessionContext."""
        messages = [
            Message(role=m["role"], content=m["content"], timestamp=m.get("timestamp", ""))
            for m in data.get("messages", [])
        ]
        return SessionContext(
            session_id=data["session_id"],
            user_id=data["user_id"],
            messages=messages,
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            expired_at=data.get("expired_at", ""),
            trace_id=data.get("trace_id", ""),
        )
    
    def save(self, session: SessionContext):
        """Save session."""
        self.storage[session.session_id] = session
    
    def delete(self, session_id: str):
        """Delete session."""
        if session_id in self.storage:
            del self.storage[session_id]
        
        # Also delete from cache if available
        if self._cache:
            self._cache.delete(f"session:{session_id}")
    
    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return self.get(session_id) is not None
    
    def list_by_user(self, user_id: str) -> List[SessionContext]:
        """List all sessions for a user."""
        return [
            s for s in self.storage.values()
            if s.user_id == user_id and not s.is_expired()
        ]
    
    def clear_expired(self):
        """Clear expired sessions."""
        expired = [
            sid for sid, s in self.storage.items()
            if s.is_expired()
        ]
        for sid in expired:
            del self.storage[sid]
        return len(expired)
    
    def to_json(self, session_id: str) -> Optional[str]:
        """Serialize session to JSON."""
        import json
        session = self.get(session_id)
        if not session:
            return None
        return json.dumps(session.to_dict(), ensure_ascii=False)
    
    def from_json(self, data: str) -> Optional[SessionContext]:
        """Deserialize session from JSON."""
        import json
        try:
            d = json.loads(data)
            return SessionContext(**d)
        except Exception:
            return None
    
    def get_session_handler(self) -> Optional[SessionHandler]:
        """Get the SessionHandler instance."""
        return self._session_handler
    
    def shutdown(self) -> None:
        """Shutdown async components gracefully."""
        if self._db_writer:
            self._db_writer.stop()
        if self._cache:
            self._cache.close()
