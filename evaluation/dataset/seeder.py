"""Seed the evaluation dataset from nonprod Langfuse traces.

TraceSeeder queries nonprod for completed coach conversations and writes
dataset items to the nonprod Langfuse dataset so the eval pipeline can
use them without needing prod data.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langfuse import Langfuse

from evaluation.dataset.schema import (
    DatasetItemExpectedOutput,
    DatasetItemInput,
    MessageDict,
)

logger = logging.getLogger(__name__)

# debt_case values that indicate the coach node ran (not escalate/comfort)
_COACH_DEBT_CASES = {"healthy", "yellow", "orange"}


@dataclass
class SeedStats:
    traces_fetched: int = 0
    traces_eligible: int = 0
    items_seeded: int = 0


def _extract_message_text(msg: Any) -> str | None:
    """Extract text content from a LangChain message dict (handles multiple serialization formats)."""
    if not isinstance(msg, dict):
        return None

    # Standard format: {"type": "human", "content": "..."}
    content = msg.get("content", "")
    if isinstance(content, str):
        return content

    # Content as list of content blocks (multimodal)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return " ".join(p for p in parts if p)

    # LangChain constructor serialization: {"id": [...], "kwargs": {"content": "..."}}
    kwargs = msg.get("kwargs", {})
    if isinstance(kwargs, dict) and "content" in kwargs:
        return kwargs["content"]

    return None


def _get_message_role(msg: Any) -> str | None:
    """Get normalised role ("user" | "assistant") from a LangChain message dict."""
    if not isinstance(msg, dict):
        return None

    msg_type = msg.get("type", "").lower()
    if msg_type in ("human", "user"):
        return "user"
    if msg_type in ("ai", "assistant"):
        return "assistant"

    # LangChain constructor format uses class names in "id" list
    id_list = msg.get("id", [])
    if isinstance(id_list, list):
        class_name = " ".join(id_list).lower()
        if "humanmessage" in class_name:
            return "user"
        if "aimessage" in class_name:
            return "assistant"

    return None


def _parse_messages(raw_messages: list[Any]) -> list[MessageDict] | None:
    """Convert a list of LangChain message dicts to our simplified MessageDict format."""
    result: list[MessageDict] = []
    for msg in raw_messages:
        role = _get_message_role(msg)
        text = _extract_message_text(msg)
        if role is None or text is None:
            logger.debug("Skipping unparseable message: %s", type(msg))
            continue
        # Skip empty messages and tool-call-only AI messages
        if not text.strip():
            continue
        result.append(MessageDict(role=role, content=text))
    return result or None


class TraceSeeder:
    def __init__(
        self,
        nonprod_client: Langfuse,
        dataset_name: str,
        max_items: int = 50,
    ) -> None:
        self.client = nonprod_client
        self.dataset_name = dataset_name
        self.max_items = max_items

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_dataset_exists(self) -> None:
        try:
            self.client.create_dataset(
                name=self.dataset_name,
                description="Money coach evaluation dataset, seeded from nonprod traces",
            )
            logger.info("Created dataset '%s'", self.dataset_name)
        except Exception:
            logger.debug("Dataset '%s' already exists", self.dataset_name)

    def _count_dataset_items(self) -> int:
        try:
            dataset = self.client.get_dataset(self.dataset_name)
            return len(dataset.items)
        except Exception:
            return 0

    def _is_eligible_trace(self, trace: Any) -> bool:
        output = trace.output
        if not isinstance(output, dict):
            return False
        if output.get("assessment_phase") != "completed":
            return False
        if output.get("debt_case", "") not in _COACH_DEBT_CASES:
            return False
        messages = output.get("messages", [])
        return isinstance(messages, list) and len(messages) >= 2

    def _trace_to_dataset_item(
        self, trace: Any
    ) -> tuple[DatasetItemInput, DatasetItemExpectedOutput] | None:
        output = trace.output
        raw_messages = output.get("messages", [])

        messages = _parse_messages(raw_messages)
        if not messages or len(messages) < 2:
            return None

        # Last message must be an assistant (coach) response
        if messages[-1]["role"] != "assistant":
            return None

        expected_message = messages[-1]["content"]
        input_messages = messages[:-1]

        if not input_messages:
            return None

        item_input = DatasetItemInput(
            messages=input_messages,
            assessment_data=output.get("assessment_data", {}),
            debt_case=output.get("debt_case", "unknown"),
            emotional_state=output.get("emotional_state", "ready"),
            assessment_phase="completed",
        )
        expected_output = DatasetItemExpectedOutput(
            final_message=expected_message,
            terminal_node="coach",
        )
        return item_input, expected_output

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def seed(self, skip_if_not_empty: bool = False, dry_run: bool = False) -> SeedStats:
        """Seed the dataset.

        Args:
            skip_if_not_empty: If True and the dataset already has items, return early.
            dry_run: Log what would be seeded without writing anything.
        """
        stats = SeedStats()

        if not dry_run:
            self._ensure_dataset_exists()

        if skip_if_not_empty and not dry_run:
            count = self._count_dataset_items()
            if count > 0:
                logger.info(
                    "Dataset '%s' already has %d items — skipping (pass --force-reseed to override)",
                    self.dataset_name,
                    count,
                )
                return stats

        page = 1
        seeded = 0

        while seeded < self.max_items:
            try:
                response = self.client.api.trace.list(
                    page=page,
                    limit=min(
                        50, self.max_items * 3
                    ),  # over-fetch to account for filtering
                )
            except Exception as exc:
                logger.error("Failed to fetch traces (page=%d): %s", page, exc)
                break

            traces = response.data
            if not traces:
                break

            stats.traces_fetched += len(traces)

            for trace in traces:
                if seeded >= self.max_items:
                    break
                if not self._is_eligible_trace(trace):
                    continue

                stats.traces_eligible += 1
                result = self._trace_to_dataset_item(trace)
                if result is None:
                    continue

                item_input, expected_output = result

                if dry_run:
                    logger.info(
                        "[DRY RUN] Would seed item from trace %s  debt_case=%s  messages=%d",
                        trace.id,
                        item_input["debt_case"],
                        len(item_input["messages"]),
                    )
                    seeded += 1
                    stats.items_seeded += 1
                else:
                    try:
                        self.client.create_dataset_item(
                            dataset_name=self.dataset_name,
                            input=dict(item_input),
                            expected_output=dict(expected_output),
                            metadata={"source_trace_id": trace.id},
                        )
                        seeded += 1
                        stats.items_seeded += 1
                        logger.debug("Seeded item from trace %s", trace.id)
                    except Exception as exc:
                        logger.warning(
                            "Failed to create dataset item from trace %s: %s",
                            trace.id,
                            exc,
                        )

            if not response.meta or page >= response.meta.total_pages:
                break
            page += 1

        return stats
