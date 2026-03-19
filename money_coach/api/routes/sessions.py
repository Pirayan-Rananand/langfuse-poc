"""Session management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from money_coach.api.deps import get_graph, get_session_store
from money_coach.api.schemas import (
    MessageItem,
    SessionHistoryResponse,
    SessionResponse,
    StateMetadata,
)
from money_coach.middleware.session import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    sessions: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    session = await sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return SessionResponse(
        session_id=session.id,
        user_id=session.user_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        metadata=session.metadata,
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    sessions: SessionStore = Depends(get_session_store),
    graph=Depends(get_graph),
) -> SessionHistoryResponse:
    session = await sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    state = await graph.aget_state({"configurable": {"thread_id": session_id}})
    if not state.values:
        return SessionHistoryResponse(
            session_id=session_id, messages=[], state=StateMetadata()
        )

    messages = [
        MessageItem(
            role=getattr(m, "type", "unknown"),
            content=getattr(m, "content", ""),
        )
        for m in state.values.get("messages", [])
    ]

    meta = StateMetadata(
        journey_phase=state.values.get("journey_phase"),
        journey_step=state.values.get("journey_step"),
        emotional_state=state.values.get("emotional_state"),
        triage_classification=state.values.get("triage_classification"),
        debt_inventory_complete=state.values.get("debt_inventory_complete", False),
        cash_flow_complete=state.values.get("cash_flow_complete", False),
        plan_confirmed=state.values.get("plan_confirmed", False),
    )

    return SessionHistoryResponse(
        session_id=session_id, messages=messages, state=meta
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    sessions: SessionStore = Depends(get_session_store),
) -> dict:
    deleted = await sessions.delete(session_id)
    if not deleted:
        raise HTTPException(404, "Session not found")
    return {"ok": True}
