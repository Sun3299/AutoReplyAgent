"""
context/async_db.py - Async database writer

Queue-based async writer that flushes to DB on interval or queue size.
Uses asyncio for background task, doesn't block main thread.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from queue import Queue
from threading import Thread
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


class AsyncDBWriter:
    """
    Async database writer with queue-based batch writes.
    
    write() adds records to queue, background task flushes when:
    - Interval reaches 5 seconds, OR
    - Queue size reaches 100 records
    
    Attributes:
        db_url: Database connection URL (SQLite if not set)
        flush_interval: Flush interval in seconds (default: 5)
        max_queue_size: Max queue size before flush (default: 100)
    """
    
    def __init__(
        self,
        db_url: Optional[str] = None,
        flush_interval: int = 5,
        max_queue_size: int = 100,
    ):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size
        
        self._queue: Queue = Queue()
        self._running = False
        self._worker_thread: Optional[Thread] = None
        self._connection = None
        self._cursor = None
        
        # Use SQLite if no database URL provided
        self._use_sqlite = not bool(self.db_url) or self.db_url.startswith("sqlite")
        self._init_db()
        self._start_worker()
    
    def _init_db(self) -> None:
        """Initialize database connection and create tables if needed."""
        # Use SQLite if no database URL provided
        self._use_sqlite = not bool(self.db_url) or self.db_url.startswith("sqlite")
        
        if self._use_sqlite:
            db_path = self.db_url.replace("sqlite:///", "") if self.db_url else "context.db"
            self._connection_path = db_path
        
        # Try to import aiosqlite, but don't fail if not available
        try:
            import aiosqlite  # noqa: F401
        except ImportError:
            logger.warning("aiosqlite not available, running without DB persistence")
    
    def _start_worker(self) -> None:
        """Start background worker thread."""
        self._running = True
        self._worker_thread = Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("AsyncDBWriter background worker started")
    
    def _worker_loop(self) -> None:
        """Background worker loop that processes the queue."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._async_worker())
        except Exception as e:
            logger.error(f"AsyncDBWriter worker error: {e}")
        finally:
            loop.close()
    
    async def _async_worker(self) -> None:
        """Async worker that handles queue processing."""
        import aiosqlite
        
        # Connect to SQLite
        conn = await aiosqlite.connect(self._connection_path)
        cursor = await conn.cursor()
        
        # Create tables if not exist
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await conn.commit()
        
        last_flush = datetime.now()
        batch: List[Dict[str, Any]] = []
        
        while self._running:
            # Collect items from queue (non-blocking)
            while not self._queue.empty() and len(batch) < self.max_queue_size:
                try:
                    item = self._queue.get_nowait()
                    batch.append(item)
                except Exception:
                    break
            
            # Check if we should flush
            time_since_flush = (datetime.now() - last_flush).total_seconds()
            should_flush = (
                len(batch) >= self.max_queue_size or
                (len(batch) > 0 and time_since_flush >= self.flush_interval)
            )
            
            if should_flush:
                await self._flush_batch(conn, cursor, batch)
                last_flush = datetime.now()
                batch = []
            
            # Sleep briefly to avoid busy waiting
            await asyncio.sleep(0.1)
        
        # Final flush on shutdown
        if batch:
            await self._flush_batch(conn, cursor, batch)
        
        await conn.close()
    
    async def _flush_batch(
        self,
        conn: 'aiosqlite.Connection',
        cursor: 'aiosqlite.Cursor',
        batch: List[Dict[str, Any]],
    ) -> None:
        """Flush a batch of records to the database."""
        if not batch:
            return
        
        try:
            for item in batch:
                await cursor.execute(
                    """
                    INSERT INTO session_events (session_id, event_type, data, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        item.get("session_id", ""),
                        item.get("event_type", ""),
                        json.dumps(item.get("data", {}), ensure_ascii=False),
                        item.get("created_at", datetime.now().isoformat()),
                    )
                )
            await conn.commit()
            logger.debug(f"Flushed {len(batch)} records to database")
        except Exception as e:
            logger.error(f"Failed to flush batch to database: {e}")
    
    def write(self, table: str, data: Dict[str, Any]) -> None:
        """
        Queue a record for async database write.
        
        Args:
            table: Table name (used as event_type in storage)
            data: Record data to persist
        """
        # Extract session_id from data if present
        session_id = data.get("session_id", "")
        
        item = {
            "session_id": session_id,
            "event_type": table,
            "data": data,
            "created_at": datetime.now().isoformat(),
        }
        
        self._queue.put(item)
    
    def write_session_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Queue a session event for async persistence.
        
        Args:
            session_id: Session ID
            event_type: Event type (e.g., 'round_save', 'state_update')
            data: Event data
        """
        item = {
            "session_id": session_id,
            "event_type": event_type,
            "data": data,
            "created_at": datetime.now().isoformat(),
        }
        
        self._queue.put(item)
    
    def stop(self) -> None:
        """Stop the background worker gracefully."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("AsyncDBWriter stopped")
    
    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
