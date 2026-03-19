"""Chat endpoints — sync response and SSE streaming."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langfuse.langchain import CallbackHandler

from money_coach.api.deps import get_graph, get_session_store
from money_coach.api.schemas import ChatRequest, ChatResponse, StateMetadata
from money_coach.middleware.session import SessionStore

router = APIRouter(prefix="/chat", tags=["chat"])


def _extract_state_metadata(state: dict) -> StateMetadata:
    return StateMetadata(
        journey_phase=state.get("journey_phase"),
        journey_step=state.get("journey_step"),
        emotional_state=state.get("emotional_state"),
        triage_classification=state.get("triage_classification"),
        debt_inventory_complete=state.get("debt_inventory_complete", False),
        cash_flow_complete=state.get("cash_flow_complete", False),
        plan_confirmed=state.get("plan_confirmed", False),
    )


def _build_config(session_id: str) -> dict:
    return {
        "configurable": {"thread_id": session_id},
        "metadata": {"langfuse_session_id": session_id},
        "callbacks": [CallbackHandler()],
    }


# ── POST /api/chat ────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    sessions: SessionStore = Depends(get_session_store),
    graph=Depends(get_graph),
) -> ChatResponse:
    # Auto-create session on first message
    if await sessions.get(body.session_id) is None:
        await sessions.create(
            session_id=body.session_id,
            user_id=body.user_id,
        )

    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": body.message}]},
        config=_build_config(body.session_id),
    )

    last_message = result["messages"][-1]
    return ChatResponse(
        session_id=body.session_id,
        message=last_message.content,
        state=_extract_state_metadata(result),
    )


# ── POST /api/chat/stream ────────────────────────────────


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    sessions: SessionStore = Depends(get_session_store),
    graph=Depends(get_graph),
) -> StreamingResponse:
    if await sessions.get(body.session_id) is None:
        await sessions.create(
            session_id=body.session_id,
            user_id=body.user_id,
        )

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": body.message}]},
                config=_build_config(body.session_id),
                version="v2",
            ):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        payload = json.dumps(
                            {"type": "token", "content": chunk.content},
                            ensure_ascii=False,
                        )
                        yield f"data: {payload}\n\n"

            # Final state snapshot
            state = await graph.aget_state(
                {"configurable": {"thread_id": body.session_id}}
            )
            meta = _extract_state_metadata(state.values) if state.values else StateMetadata()
            yield f"data: {json.dumps({'type': 'done', 'state': meta.model_dump()}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
