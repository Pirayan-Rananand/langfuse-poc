import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from money_coach.state import State

logger = logging.getLogger(__name__)


class EmotionalDecision(BaseModel):
    is_distressed: bool


class EmotionalGateNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str) -> None:
        structured_llm = llm.with_structured_output(EmotionalDecision)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("placeholder", "{messages}"),
        ])
        self._chain = prompt | structured_llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        try:
            decision: EmotionalDecision = self._chain.invoke(
                {"messages": state["messages"]}, config=config
            )
            emotional_state = "distressed" if decision.is_distressed else "ready"
        except Exception as exc:
            logger.warning("EmotionalGateNode failed (%s) — defaulting to ready", exc)
            emotional_state = "ready"
        return {"emotional_state": emotional_state}
