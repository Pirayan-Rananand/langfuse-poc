from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    emotional_state: str      # "unknown" | "ready" | "distressed"
    assessment_phase: str     # "not_started" | "in_progress" | "completed"
    assessment_data: dict     # accumulated financial answers
    debt_case: str            # "unknown" | "healthy" | "yellow" | "orange" | "red"
