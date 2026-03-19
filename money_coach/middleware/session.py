"""Session management for Money Coach conversations.

Production (Cloud SQL):
  Store sessions in a ``sessions`` table:
    CREATE TABLE sessions (
        id          TEXT PRIMARY KEY,
        user_id     TEXT,
        created_at  TIMESTAMPTZ DEFAULT now(),
        updated_at  TIMESTAMPTZ DEFAULT now(),
        metadata    JSONB DEFAULT '{}'
    );

Local dev:
  InMemorySessionStore — sessions lost on restart.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Session:
    id: str
    user_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


class SessionStore(ABC):
    """Abstract interface — swap implementations without touching callers."""

    @abstractmethod
    async def create(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session: ...

    @abstractmethod
    async def get(self, session_id: str) -> Session | None: ...

    @abstractmethod
    async def update_metadata(self, session_id: str, metadata: dict) -> Session | None: ...

    @abstractmethod
    async def delete(self, session_id: str) -> bool: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[Session]: ...


class InMemorySessionStore(SessionStore):
    """Dict-backed session store — suitable for local dev and tests."""

    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    async def create(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        sid = session_id or uuid.uuid4().hex
        session = Session(id=sid, user_id=user_id, metadata=metadata or {})
        self._store[sid] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    async def update_metadata(self, session_id: str, metadata: dict) -> Session | None:
        session = self._store.get(session_id)
        if session is None:
            return None
        session.metadata.update(metadata)
        session.updated_at = datetime.now(timezone.utc)
        return session

    async def delete(self, session_id: str) -> bool:
        return self._store.pop(session_id, None) is not None

    async def list_by_user(self, user_id: str) -> list[Session]:
        return [s for s in self._store.values() if s.user_id == user_id]


# TODO: CloudSQLSessionStore(SessionStore) — backed by asyncpg / SQLAlchemy async.
