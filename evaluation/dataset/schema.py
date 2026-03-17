"""Dataset item types for the evaluation pipeline."""

from typing import Any

from typing_extensions import TypedDict


class MessageDict(TypedDict):
    role: str    # "user" | "assistant"
    content: str


class DatasetItemInput(TypedDict):
    messages: list[MessageDict]
    assessment_data: dict[str, Any]
    debt_case: str           # "healthy" | "yellow" | "orange"
    emotional_state: str     # always "ready" in dataset
    assessment_phase: str    # always "completed" — routes graph directly to coach


class DatasetItemExpectedOutput(TypedDict):
    final_message: str       # original coach response (gold reference)
    terminal_node: str       # always "coach"
