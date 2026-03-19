"""Request / response models for the Money Coach API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: str = Field(description="Conversation thread ID (UUID recommended)")
    message: str = Field(description="User message text")
    user_id: str | None = Field(default=None, description="Optional user identifier")


# ── Responses ─────────────────────────────────────────────


class StateMetadata(BaseModel):
    """Subset of graph state exposed to the frontend."""

    journey_phase: str | None = None
    journey_step: str | None = None
    emotional_state: str | None = None
    triage_classification: str | None = None
    debt_inventory_complete: bool = False
    cash_flow_complete: bool = False
    plan_confirmed: bool = False


class ChatResponse(BaseModel):
    session_id: str
    message: str
    state: StateMetadata


class SessionResponse(BaseModel):
    session_id: str
    user_id: str | None = None
    created_at: str
    updated_at: str
    metadata: dict = Field(default_factory=dict)


class MessageItem(BaseModel):
    role: str
    content: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]
    state: StateMetadata


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    database: str = "disconnected"


class ErrorResponse(BaseModel):
    detail: str
