from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from money_coach.state import State


class ClarifyNode:
    def __init__(self, clarifier_chain) -> None:
        self._chain = clarifier_chain

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        try:
            decision = self._chain.invoke(
                {"messages": state["messages"]}, config=config
            )
        except Exception:
            # Never block the user if the clarifier fails (e.g. malformed JSON)
            return {"needs_clarification": False}

        if decision.needs_clarification:
            questions = "\n".join(f"- {q}" for q in decision.questions)
            reply = (
                "Before I can give you accurate advice, I need a bit more detail:"
                f"\n\n{questions}"
            )
            return {
                "messages": [AIMessage(content=reply)],
                "needs_clarification": True,
            }

        return {"needs_clarification": False}
