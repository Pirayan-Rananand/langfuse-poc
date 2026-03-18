import json
import logging
import re
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, field_validator

from money_coach.state import State

logger = logging.getLogger(__name__)


def _parse_numeric(v: Any) -> Optional[float]:
    """Parse a numeric value that may be a plain number or a range string.

    Handles:
      - None / float / int  -> passthrough
      - "48,000"            -> 48000.0   (thousands-separator comma)
      - "48,000 - 60,000"   -> 54000.0   (midpoint of range)
      - "48000-60000"        -> 54000.0
    """
    if v is None or isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if isinstance(v, str):
        cleaned = v.replace(",", "").strip()
        # Range: two numbers separated by a dash (allow spaces around dash)
        m = re.match(r"^(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)$", cleaned)
        if m:
            return (float(m.group(1)) + float(m.group(2))) / 2
        return float(cleaned)
    return float(v)


class CashFlowData(BaseModel):
    monthly_income: Optional[float] = None
    fixed_expenses: Optional[float] = None
    variable_expenses: Optional[float] = None
    desired_monthly_savings: Optional[float] = None

    @field_validator(
        "monthly_income",
        "fixed_expenses",
        "variable_expenses",
        "desired_monthly_savings",
        mode="before",
    )
    @classmethod
    def parse_numeric(cls, v: Any) -> Optional[float]:
        return _parse_numeric(v)


class CashFlowOutput(BaseModel):
    updated_cash_flow: CashFlowData
    next_question: Optional[str] = Field(
        default=None,
        description="คำถามถัดไปที่ต้องถามผู้ใช้ (None เมื่อข้อมูลครบแล้ว)",
    )
    is_complete: bool = Field(
        description="True เมื่อมีข้อมูลกระแสเงินสดครบทุกส่วนที่จำเป็น",
    )


class CashFlowNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str, langfuse_prompt=None) -> None:
        structured_llm = llm.with_structured_output(CashFlowOutput)
        metadata = {"langfuse_prompt": langfuse_prompt} if langfuse_prompt else {}
        prompt = ChatPromptTemplate(
            [("system", system_prompt), ("placeholder", "{messages}")],
            metadata=metadata,
        )
        self._chain = prompt | structured_llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        cash_flow_data = state.get("cash_flow_data") or {}
        cash_flow_data_json = json.dumps(cash_flow_data, ensure_ascii=False, indent=2)

        try:
            output: CashFlowOutput = self._chain.invoke(
                {
                    "messages": state["messages"],
                    "cash_flow_data": cash_flow_data_json,
                },
                config=config,
            )
        except Exception as exc:
            logger.warning("CashFlowNode failed (%s) — returning safe fallback", exc)
            return {
                "cash_flow_complete": False,
                "messages": [
                    AIMessage(
                        content="ขอโทษนะคะ เกิดข้อผิดพลาดชั่วคราว กรุณาลองตอบใหม่อีกครั้งค่ะ"
                    )
                ],
            }

        updated_data = output.updated_cash_flow.model_dump()

        if output.is_complete:
            return {
                "cash_flow_data": updated_data,
                "cash_flow_complete": True,
            }

        result: dict = {
            "cash_flow_data": updated_data,
            "cash_flow_complete": False,
        }
        if output.next_question:
            result["messages"] = [AIMessage(content=output.next_question)]
        return result
