"""
context/session_handler.py - Session persistence layer

Integrates SessionManager with Redis cache and async DB writer.
Handles session lifecycle: create, save, get, update, refresh.

Session data cached: session_id, user_id, channel, rounds (last 5 only),
state, updated_at

File persistence: channels/{channel}/memory/sessions.jsonl
"""

import logging
import uuid
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from session.session_manager import SessionManager

logger = logging.getLogger(__name__)


class SessionHandler:
    """
    Session persistence handler.

    Integrates:
    - SessionManager: in-memory session storage
    - RedisCache: session state caching (optional)
    - AsyncDBWriter: async persistence to database (optional)
    - FilePersistence: jsonl file per channel (channels/{channel}/memory/)

    Attributes:
        cache_ttl: Cache TTL in seconds (default: 1800 = 30 minutes)
        max_cached_rounds: Max rounds to store in cache (default: 5)
    """

    def __init__(
        self,
        cache: Optional["RedisCache"] = None,
        db_writer: Optional["AsyncDBWriter"] = None,
        cache_ttl: int = 1800,
        max_cached_rounds: int = 5,
    ):
        """
        Initialize SessionHandler.

        Args:
            cache: RedisCache instance (optional)
            db_writer: AsyncDBWriter instance (optional)
            cache_ttl: Cache TTL in seconds
            max_cached_rounds: Max rounds to store in cache
        """
        self._session_manager = SessionManager()
        self._cache = cache
        self._db_writer = db_writer
        self.cache_ttl = cache_ttl
        self.max_cached_rounds = max_cached_rounds

    def create_session(
        self,
        user_id: str,
        channel: str = "web",
        session_type: str = "general",
    ) -> Dict[str, Any]:
        """
        Create a new session.

        Args:
            user_id: User ID
            channel: Source channel
            session_type: Session type

        Returns:
            Session data dict
        """
        # Create in-memory session
        session = self._session_manager.create_session(
            user_id=user_id,
            channel=channel,
            session_type=session_type,
        )

        # Build session data for caching/persistence
        session_data = self._build_session_data(session)

        # Cache in Redis
        self._cache_session(session.session_id, session_data)

        # Queue for async DB persistence
        self._persist_session(session.session_id, "create", session_data)

        logger.info(f"Created session: {session.session_id} for user: {user_id}")

        return session_data

    def save_round(
        self,
        session_id: str,
        role: str,
        content: str,
        channel: str = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Save a conversation round.

        Args:
            session_id: Session ID
            role: Role (user/assistant)
            content: Message content
            channel: Channel (optional, for file persistence)

        Returns:
            (updated_session_data, truncate_marker or None)
        """
        # Save to in-memory session manager
        session, truncate_marker = self._session_manager.save_round(
            session_id=session_id,
            role=role,
            content=content,
        )

        # 保存到文件（不依赖 session_manager）
        target_channel = None
        if session and session.channel:
            target_channel = session.channel
        elif channel:
            target_channel = channel

        if target_channel:
            self._append_to_session_file(target_channel, session_id, role, content)

        if not session:
            return None, None

        # Build updated session data
        session_data = self._build_session_data(session)

        # Update cache
        self._cache_session(session_id, session_data)

        # Queue for async DB persistence
        self._persist_session(session_id, "round_save", session_data)

        # 同时写入文件持久化（按 channel + session 分类）
        if session.channel:
            self._append_to_session_file(session.channel, session_id, role, content)

        # Build truncate marker dict if present
        marker_dict = None
        if truncate_marker:
            marker_dict = truncate_marker.to_dict()

        return session_data, marker_dict

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session by ID.

        First checks cache, then falls back to SessionManager.

        Args:
            session_id: Session ID

        Returns:
            Session data dict or None if not found
        """
        # Try cache first
        if self._cache:
            cached = self._cache.get(f"session:{session_id}")
            if cached:
                logger.debug(f"Cache hit for session: {session_id}")
                return cached

        # Fall back to SessionManager
        session = self._session_manager.get_session(session_id)
        if not session:
            return None

        # Build and cache session data
        session_data = self._build_session_data(session)
        self._cache_session(session_id, session_data)

        return session_data

    def update_state(
        self,
        session_id: str,
        state: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Update session state.

        Args:
            session_id: Session ID
            state: State dict (strings only)

        Returns:
            Updated session data dict or None if not found
        """
        session = self._session_manager.update_state(session_id, state)
        if not session:
            return None

        # Build updated session data
        session_data = self._build_session_data(session)

        # Update cache
        self._cache_session(session_id, session_data)

        # Queue for async DB persistence
        self._persist_session(session_id, "state_update", session_data)

        return session_data

    def refresh_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Refresh session expiration.

        Args:
            session_id: Session ID

        Returns:
            Updated session data dict or None if not found
        """
        session = self._session_manager.refresh_session(session_id)
        if not session:
            return None

        # Build updated session data
        session_data = self._build_session_data(session)

        # Update cache TTL
        self._cache_session(session_id, session_data)

        # Queue for async DB persistence
        self._persist_session(session_id, "refresh", session_data)

        return session_data

    def _build_session_data(self, session: "SessionContext") -> Dict[str, Any]:
        """
        Build session data dict for caching/persistence.

        Only includes last N rounds to limit cache size.

        Args:
            session: SessionContext from SessionManager

        Returns:
            Session data dict
        """
        # Only keep last N rounds for caching
        cached_rounds = (
            session.rounds[-self.max_cached_rounds :] if session.rounds else []
        )

        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "channel": session.channel,
            "rounds": [r.to_dict() for r in cached_rounds],
            "state": session.state,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "expire_at": session.expire_at,
        }

    def _cache_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """
        Cache session data in Redis.

        Args:
            session_id: Session ID
            session_data: Session data to cache
        """
        if not self._cache:
            return

        cache_key = f"session:{session_id}"
        success = self._cache.set(cache_key, session_data, ttl=self.cache_ttl)

        if success:
            logger.debug(f"Cached session: {session_id}")
        else:
            logger.warning(f"Failed to cache session: {session_id}")

    def _persist_session(
        self,
        session_id: str,
        event_type: str,
        session_data: Dict[str, Any],
    ) -> None:
        """
        Queue session for async database persistence.

        Args:
            session_id: Session ID
            event_type: Event type
            session_data: Session data to persist
        """
        if not self._db_writer:
            return

        self._db_writer.write_session_event(
            session_id=session_id,
            event_type=event_type,
            data=session_data,
        )

        logger.debug(f"Queued session for persistence: {session_id} ({event_type})")

    def get_state(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get session state."""
        return self._session_manager.get_state(session_id)

    def get_rounds(
        self,
        session_id: str,
        keep_rounds: Optional[int] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """Get session rounds."""
        rounds, marker = self._session_manager.get_rounds(session_id, keep_rounds)

        rounds_dict = None
        if rounds:
            rounds_dict = [r.to_dict() for r in rounds]

        marker_dict = None
        if marker:
            marker_dict = marker.to_dict()

        return rounds_dict, marker_dict

    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all active sessions for a user."""
        sessions = self._session_manager.get_user_sessions(user_id)
        return [self._build_session_data(s) for s in sessions]

    def clear_session(self, session_id: str) -> bool:
        """Clear a session completely."""
        # Clear from cache
        if self._cache:
            self._cache.delete(f"session:{session_id}")

        # Clear from session manager
        return self._session_manager.clear_session(session_id)

    # ==================== File Persistence ====================

    def _get_memory_dir(self, channel: str) -> str:
        """
        获取 channel 对应的 memory 目录路径

        Args:
            channel: 渠道名称

        Returns:
            目录路径
        """
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 构建路径: channels/{channel}/memory/
        memory_dir = os.path.join(project_root, "channels", channel, "memory")

        # 确保目录存在
        os.makedirs(memory_dir, exist_ok=True)

        return memory_dir

    def _get_session_file_path(self, channel: str, session_id: str) -> str:
        """
        获取 session 对应的文件路径

        Args:
            channel: 渠道名称
            session_id: 会话ID

        Returns:
            完整的文件路径: channels/{channel}/memory/{session_id}.jsonl
        """
        memory_dir = self._get_memory_dir(channel)
        # 清理 session_id 中的非法字符（Windows 不允许 : \ / * ? " < > |）
        safe_session_id = (
            session_id.replace(":", "_").replace("\\", "_").replace("/", "_")
        )
        return os.path.join(memory_dir, f"{safe_session_id}.jsonl")

    def _load_session_from_file(
        self, channel: str, session_id: str
    ) -> List[Dict[str, Any]]:
        """
        从文件加载指定 session 的所有记录

        Args:
            channel: 渠道名称
            session_id: 会话ID

        Returns:
            记录列表
        """
        file_path = self._get_session_file_path(channel, session_id)

        if not os.path.exists(file_path):
            return []

        records = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning(f"Failed to load session from {file_path}: {e}")

        return records

    def _append_to_session_file(
        self,
        channel: str,
        session_id: str,
        role: str,
        content: str,
        request_id: str = "",
    ):
        """
        追加一条记录到 session 文件

        Args:
            channel: 渠道名称
            session_id: 会话ID
            role: 角色 (user/assistant)
            content: 消息内容
            request_id: 请求ID（用于链路追踪）
        """
        file_path = self._get_session_file_path(channel, session_id)

        record = {
            "type": role,
            "content": content,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "request_id": request_id,
        }

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.debug(f"Appended to {file_path}: {role}, request_id={request_id}")
        except Exception as e:
            logger.warning(f"Failed to append to {file_path}: {e}")

    def save_session_to_file(
        self,
        channel: str,
        session_id: str,
        role: str,
        content: str,
        request_id: str = "",
    ):
        """
        保存 session 记录到文件（公开方法）

        Args:
            channel: 渠道名称
            session_id: 会话ID
            role: 角色 (user/assistant)
            content: 消息内容
            request_id: 请求ID（用于链路追踪）
        """
        self._append_to_session_file(channel, session_id, role, content, request_id)

    def get_session_history_from_file(
        self, channel: str, session_id: str = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        从文件获取 session 历史记录

        Args:
            channel: 渠道名称
            session_id: 会话ID（必填）
            limit: 返回条数限制

        Returns:
            session 记录列表
        """
        if not session_id:
            return []

        records = self._load_session_from_file(channel, session_id)

        # 返回最近 limit 条
        return records[-limit:] if limit > 0 else records
