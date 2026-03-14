import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from money_coach.state import State

logger = logging.getLogger(__name__)


class ClassificationResult(BaseModel):
    case: str       # "healthy" | "yellow" | "orange" | "red"
    rationale: str
    thai_summary: str


class ClassifierNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str) -> None:
        structured_llm = llm.with_structured_output(ClassificationResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("placeholder", "{messages}"),
        ])
        self._chain = prompt | structured_llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        assessment_data = state.get("assessment_data") or {}
        assessment_data_json = json.dumps(
            assessment_data, ensure_ascii=False, indent=2
        )

        try:
            result: ClassificationResult = self._chain.invoke(
                {
                    "messages": state["messages"],
                    "assessment_data": assessment_data_json,
                },
                config=config,
            )
        except Exception as exc:
            logger.warning(
                "ClassifierNode failed (%s) — defaulting to orange", exc
            )
            return {
                "debt_case": "orange",
                "messages": [
                    AIMessage(
                        content="ขอบคุณที่ให้ข้อมูลครบแล้วนะคะ ขอวิเคราะห์สักครู่..."
                    )
                ],
            }

        debt_case = result.case.lower()
        return {
            "debt_case": debt_case,
            "messages": [AIMessage(content=result.thai_summary)],
        }
