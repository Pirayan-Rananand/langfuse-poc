"""FastAPI application factory for Money Coach.

Usage:
    # Development
    just serve

    # Direct
    uv run uvicorn money_coach.api.server:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from money_coach.api.deps import get_database_pool
from money_coach.api.routes import api_router
from money_coach.middleware.tracing import LangfuseTracingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    db = get_database_pool()
    await db.connect()
    yield
    # Shutdown
    await db.disconnect()


app = FastAPI(
    title="Money Coach API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware (outermost first) ──────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LangfuseTracingMiddleware)

# ── Routes ────────────────────────────────────────────────

app.include_router(api_router)
