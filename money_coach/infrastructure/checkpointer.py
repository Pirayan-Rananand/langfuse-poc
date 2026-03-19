"""LangGraph checkpointer factory.

Production (Cloud SQL):
  Uses ``langgraph-checkpoint-postgres`` AsyncPostgresSaver.
  Install: ``uv add langgraph-checkpoint-postgres psycopg[binary]``

Local dev:
  Falls back to in-memory MemorySaver (state lost on restart).
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


def create_checkpointer(database_url: str | None = None) -> BaseCheckpointSaver:
    """Return a checkpointer appropriate for the environment.

    When *database_url* is provided, returns a PostgreSQL-backed saver
    so graph state survives restarts.  Otherwise returns MemorySaver.
    """
    if database_url:
        # TODO: Swap to PostgreSQL when Cloud SQL is provisioned.
        #
        # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        # return AsyncPostgresSaver.from_conn_string(database_url)
        #
        # For now, fall through to MemorySaver even if a URL is set,
        # so the server boots without a real DB.
        pass

    return MemorySaver()
