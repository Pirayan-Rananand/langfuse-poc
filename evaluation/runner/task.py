"""Task factory: wraps an eval graph as a simple callable for dataset items."""

from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage

from evaluation.dataset.schema import DatasetItemInput

TaskFunction = Callable[[DatasetItemInput], str | None]


def make_task(graph) -> TaskFunction:
    """Return a callable that runs `graph` on a DatasetItemInput and returns the
    final assistant message text, or None if the graph produced no AI output."""

    def task(item_input: DatasetItemInput) -> str | None:
        messages = []
        for m in item_input["messages"]:
            if m["role"] == "user":
                messages.append(HumanMessage(content=m["content"]))
            else:
                messages.append(AIMessage(content=m["content"]))

        state = {
            "messages": messages,
            "assessment_data": item_input.get("assessment_data", {}),
            "debt_case": item_input.get("debt_case", "unknown"),
            "emotional_state": item_input.get("emotional_state", "ready"),
            "assessment_phase": item_input.get("assessment_phase", "completed"),
        }

        result = graph.invoke(state)

        # Return the last AI message from the result
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return None

    return task
