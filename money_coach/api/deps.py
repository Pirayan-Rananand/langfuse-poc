"""FastAPI dependency injection — wires infrastructure + middleware + graph."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from money_coach.configs import agent_config
from money_coach.infrastructure.checkpointer import create_checkpointer
from money_coach.infrastructure.database import DatabasePool
from money_coach.middleware.session import InMemorySessionStore, SessionStore

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


@lru_cache(maxsize=1)
def get_database_pool() -> DatabasePool:
    return DatabasePool(url=os.getenv("DATABASE_URL"))


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    # TODO: Swap to CloudSQLSessionStore when DATABASE_URL is set
    return InMemorySessionStore()


@lru_cache(maxsize=1)
def get_graph() -> CompiledStateGraph:
    """Build the Money Coach graph with a persistent checkpointer."""
    from money_coach.graph.graph import build_graph

    db_url = os.getenv("DATABASE_URL")
    checkpointer = create_checkpointer(db_url)
    return build_graph(agent_config, checkpointer=checkpointer)
