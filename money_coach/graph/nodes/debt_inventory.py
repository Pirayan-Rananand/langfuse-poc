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
      - None / float / int  → passthrough
      - "48,000"            → 48000.0   (thousands-separator comma)
      - "48,000 - 60,000"   → 54000.0   (midpoint of range)
      - "48000-60000"       → 54000.0
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


class DebtItem(BaseModel):
    creditor: str = Field(description="ชื่อเจ้าหนี้หรือสถาบันการเงิน")
    outstanding_balance: float = Field(description="ยอดหนี้คงค้าง (บาท)")
    annual_interest_rate: float = Field(description="อัตราดอกเบี้ยต่อปี (%)")
    minimum_monthly_payment: float = Field(description="ยอดผ่อนขั้นต่ำต่อเดือน (บาท)")
    is_overdue: bool = Field(default=False, description="ค้างชำระหรือไม่")

    @field_validator(
        "outstanding_balance",
        "annual_interest_rate",
        "minimum_monthly_payment",
        mode="before",
    )
    @classmethod
    def parse_debt_numeric(cls, v: Any) -> Optional[float]:
        return _parse_numeric(v)


class DebtInventoryOutput(BaseModel):
    updated_debts: list[DebtItem] = Field(
        description="รายการหนี้ทั้งหมดที่รวบรวมได้ (รวมเดิม + ใหม่)",
    )
    next_question: Optional[str] = Field(
        default=None,
        description="คำถามถัดไปเกี่ยวกับหนี้สิน (None เมื่อข้อมูลครบแล้ว)",
    )
    is_complete: bool = Field(
        description="True เมื่อรวบรวมข้อมูลหนี้สินครบทุกรายการแล้ว",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="คำเตือน เช่น negative amortization",
    )


class DebtInventoryNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str, langfuse_prompt=None) -> None:
        structured_llm = llm.with_structured_output(DebtInventoryOutput)
        metadata = {"langfuse_prompt": langfuse_prompt} if langfuse_prompt else {}
        prompt = ChatPromptTemplate(
            [("system", system_prompt), ("placeholder", "{messages}")],
            metadata=metadata,
        )
        self._chain = prompt | structured_llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        existing_debts = state.get("debt_inventory") or []
        debt_inventory_json = json.dumps(existing_debts, ensure_ascii=False, indent=2)

        try:
            output: DebtInventoryOutput = self._chain.invoke(
                {
                    "messages": state["messages"],
                    "debt_inventory": debt_inventory_json,
                },
                config=config,
            )
        except Exception as exc:
            logger.warning("DebtInventoryNode failed (%s) — returning safe fallback", exc)
            return {
                "messages": [
                    AIMessage(
                        content="ขอโทษนะคะ เกิดข้อผิดพลาดชั่วคราว กรุณาลองบอกข้อมูลหนี้สินใหม่อีกครั้งค่ะ"
                    )
                ],
            }

        # Log any warnings from the LLM (e.g., negative amortization)
        for warning in output.warnings:
            logger.info("DebtInventory warning: %s", warning)

        updated_inventory = [item.model_dump() for item in output.updated_debts]

        if output.is_complete:
            # Build completion message from next_question or a default
            completion_message = output.next_question or "ข้อมูลหนี้สินครบถ้วนแล้วค่ะ เราจะไปขั้นตอนถัดไปนะคะ"
            return {
                "debt_inventory": updated_inventory,
                "debt_inventory_complete": True,
                "journey_phase": "cash_flow",
                "journey_step": "",
                "messages": [AIMessage(content=completion_message)],
            }

        result: dict = {
            "debt_inventory": updated_inventory,
        }
        if output.next_question:
            result["messages"] = [AIMessage(content=output.next_question)]

        # Include warnings in the message if present
        if output.warnings:
            warning_text = "\n".join(f"⚠️ {w}" for w in output.warnings)
            if "messages" in result:
                existing_content = result["messages"][0].content
                result["messages"] = [
                    AIMessage(content=f"{warning_text}\n\n{existing_content}")
                ]
            else:
                result["messages"] = [AIMessage(content=warning_text)]

        return result
