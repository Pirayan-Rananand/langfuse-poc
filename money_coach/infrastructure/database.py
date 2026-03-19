"""Cloud SQL connection pool — placeholder for GCP infrastructure.

Production setup:
  1. Deploy Cloud SQL PostgreSQL instance
  2. Use Cloud SQL Auth Proxy (sidecar) for secure connections
  3. Set DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/moneycoach

Local dev:
  Leave DATABASE_URL unset → services fall back to in-memory stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DatabasePool:
    """Async connection pool for Cloud SQL PostgreSQL.

    Currently a placeholder — all consumers fall back to in-memory
    implementations when ``url`` is ``None``.
    """

    url: str | None = None
    pool_size: int = 5
    max_overflow: int = 10
    _connected: bool = field(default=False, init=False, repr=False)

    async def connect(self) -> None:
        if not self.url:
            return
        # TODO: Initialize async connection pool
        # from sqlalchemy.ext.asyncio import create_async_engine
        # self._engine = create_async_engine(
        #     self.url,
        #     pool_size=self.pool_size,
        #     max_overflow=self.max_overflow,
        # )
        self._connected = True

    async def disconnect(self) -> None:
        if not self._connected:
            return
        # TODO: Dispose engine / close pool
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
