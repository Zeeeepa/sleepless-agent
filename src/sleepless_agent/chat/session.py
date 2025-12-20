"""Chat session management for interactive Slack conversations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)


class ChatSessionStatus(str, Enum):
    """Status of a chat session."""

    ACTIVE = "active"
    WAITING_FOR_INPUT = "waiting_for_input"
    PROCESSING = "processing"
    ENDED = "ended"
    ERROR = "error"


@dataclass
class ChatMessage:
    """A single message in the chat history."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChatSession:
    """Represents an active chat session."""

    session_id: str  # Unique identifier (user_id + timestamp)
    user_id: str
    channel_id: str
    thread_ts: str  # Slack thread timestamp - the parent message
    project_id: str  # Required - project identifier
    project_name: str  # Human-readable project name
    workspace_path: Optional[str] = None
    conversation_history: List[ChatMessage] = field(default_factory=list)
    status: ChatSessionStatus = ChatSessionStatus.ACTIVE
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_activity: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error_message: Optional[str] = None

    def add_message(
        self, role: str, content: str, metadata: Optional[Dict] = None
    ) -> None:
        """Add a message to conversation history."""
        self.conversation_history.append(
            ChatMessage(role=role, content=content, metadata=metadata)
        )
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def get_context_for_claude(self, max_messages: int = 10) -> str:
        """Format conversation history for Claude prompt context."""
        if not self.conversation_history:
            return ""

        # Get last N messages for context
        recent_messages = self.conversation_history[-max_messages:]

        context_parts = ["## Conversation History"]
        for msg in recent_messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            context_parts.append(f"\n**{role_label}:** {msg.content}")

        return "\n".join(context_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary for persistence."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "thread_ts": self.thread_ts,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "workspace_path": self.workspace_path,
            "conversation_history": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in self.conversation_history
            ],
            "status": self.status.value,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSession":
        """Deserialize session from dictionary."""
        session = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            channel_id=data["channel_id"],
            thread_ts=data["thread_ts"],
            project_id=data["project_id"],
            project_name=data["project_name"],
            workspace_path=data.get("workspace_path"),
            status=ChatSessionStatus(data.get("status", "active")),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            last_activity=data.get(
                "last_activity", datetime.now(timezone.utc).isoformat()
            ),
            error_message=data.get("error_message"),
        )
        for msg_data in data.get("conversation_history", []):
            session.conversation_history.append(
                ChatMessage(
                    role=msg_data["role"],
                    content=msg_data["content"],
                    timestamp=msg_data.get("timestamp", ""),
                )
            )
        return session


class ChatSessionManager:
    """Manages active chat sessions across users.

    Thread-safe session management with optional persistence to JSON file.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize session manager.

        Args:
            storage_path: Optional path for JSON persistence. If provided,
                         sessions will be saved/loaded from this file.
        """
        self._sessions: Dict[str, ChatSession] = {}  # keyed by user_id
        self._thread_index: Dict[str, str] = {}  # thread_ts -> user_id for fast lookup
        self._lock = Lock()
        self.storage_path = storage_path

        if storage_path:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_sessions()

    def create_session(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str,
        project_id: str,
        project_name: str,
        workspace_path: Optional[str] = None,
    ) -> ChatSession:
        """Create a new chat session for a user.

        If user has an existing active session, it will be ended first.
        """
        with self._lock:
            # End any existing session for this user
            if user_id in self._sessions:
                old_session = self._sessions[user_id]
                old_session.status = ChatSessionStatus.ENDED
                # Remove from thread index
                if old_session.thread_ts in self._thread_index:
                    del self._thread_index[old_session.thread_ts]

            session_id = f"{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                project_id=project_id,
                project_name=project_name,
                workspace_path=workspace_path,
            )
            self._sessions[user_id] = session
            self._thread_index[thread_ts] = user_id
            self._persist()

            logger.info(
                "chat.session.created",
                session_id=session_id,
                user_id=user_id,
                project_id=project_id,
            )
            return session

    def get_session(self, user_id: str) -> Optional[ChatSession]:
        """Get active session for a user."""
        with self._lock:
            session = self._sessions.get(user_id)
            if session and session.status != ChatSessionStatus.ENDED:
                return session
            return None

    def get_session_by_thread(self, thread_ts: str) -> Optional[ChatSession]:
        """Get session by Slack thread timestamp.

        This is the primary lookup method for routing thread messages.
        """
        with self._lock:
            user_id = self._thread_index.get(thread_ts)
            if user_id:
                session = self._sessions.get(user_id)
                if session and session.status != ChatSessionStatus.ENDED:
                    return session
            return None

    def update_session_status(
        self, user_id: str, status: ChatSessionStatus, error_message: Optional[str] = None
    ) -> None:
        """Update session status."""
        with self._lock:
            if user_id in self._sessions:
                self._sessions[user_id].status = status
                self._sessions[user_id].last_activity = (
                    datetime.now(timezone.utc).isoformat()
                )
                if error_message:
                    self._sessions[user_id].error_message = error_message
                self._persist()

    def end_session(self, user_id: str) -> Optional[ChatSession]:
        """End a user's chat session."""
        with self._lock:
            if user_id in self._sessions:
                session = self._sessions[user_id]
                session.status = ChatSessionStatus.ENDED
                session.last_activity = datetime.now(timezone.utc).isoformat()

                # Remove from thread index
                if session.thread_ts in self._thread_index:
                    del self._thread_index[session.thread_ts]

                self._persist()
                logger.info(
                    "chat.session.ended",
                    session_id=session.session_id,
                    user_id=user_id,
                    messages=len(session.conversation_history),
                )
                return session
            return None

    def is_user_in_chat_mode(self, user_id: str) -> bool:
        """Check if user has an active chat session."""
        session = self.get_session(user_id)
        return session is not None and session.status != ChatSessionStatus.ENDED

    def cleanup_stale_sessions(self, max_idle_minutes: int = 30) -> List[ChatSession]:
        """End sessions that have been inactive for too long.

        Args:
            max_idle_minutes: Maximum idle time before auto-ending session

        Returns:
            List of sessions that were ended
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_idle_minutes)
        stale_sessions = []

        with self._lock:
            for user_id, session in list(self._sessions.items()):
                if session.status == ChatSessionStatus.ENDED:
                    continue
                try:
                    last_activity = datetime.fromisoformat(
                        session.last_activity.replace("Z", "+00:00")
                    )
                    if last_activity < cutoff:
                        session.status = ChatSessionStatus.ENDED
                        stale_sessions.append(session)
                        # Remove from thread index
                        if session.thread_ts in self._thread_index:
                            del self._thread_index[session.thread_ts]
                        logger.info(
                            "chat.session.timeout",
                            session_id=session.session_id,
                            idle_minutes=max_idle_minutes,
                        )
                except Exception as e:
                    logger.warning(f"Error checking session staleness: {e}")

            if stale_sessions:
                self._persist()

        return stale_sessions

    def get_all_active_sessions(self) -> List[ChatSession]:
        """Get all active (non-ended) sessions."""
        with self._lock:
            return [
                s for s in self._sessions.values() if s.status != ChatSessionStatus.ENDED
            ]

    def _persist(self) -> None:
        """Persist sessions to storage file."""
        if not self.storage_path:
            return
        try:
            data = {uid: s.to_dict() for uid, s in self._sessions.items()}
            tmp_path = self.storage_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(self.storage_path)
        except Exception as e:
            logger.error(f"Failed to persist chat sessions: {e}")

    def _load_sessions(self) -> None:
        """Load sessions from storage file."""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for uid, session_data in data.items():
                session = ChatSession.from_dict(session_data)
                self._sessions[uid] = session
                # Rebuild thread index for active sessions
                if session.status != ChatSessionStatus.ENDED:
                    self._thread_index[session.thread_ts] = uid
            logger.info(f"Loaded {len(self._sessions)} chat sessions from storage")
        except Exception as e:
            logger.warning(f"Failed to load chat sessions: {e}")
