import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from money_coach.state import State

logger = logging.getLogger(__name__)


class WelcomeOutput(BaseModel):
    message: str = Field(
        description="ข้อความภาษาไทยที่จะแสดงให้ผู้ใช้เห็น",
    )
    next_step: str = Field(
        description="journey_step ถัดไปที่ควรเปลี่ยนไป",
    )
    pdpa_consented: Optional[bool] = Field(
        default=None,
        description="ตั้งเป็น True เมื่อผู้ใช้ยินยอม PDPA",
    )
    num_creditors: Optional[int] = Field(
        default=None,
        description="จำนวนเจ้าหนี้ที่สกัดจากคำตอบ stress_q1",
    )
    missing_payments: Optional[bool] = Field(
        default=None,
        description="ผู้ใช้มีการค้างชำระหรือไม่ จาก stress_q2",
    )
    income_covers_bills: Optional[bool] = Field(
        default=None,
        description="รายได้ครอบคลุมค่าใช้จ่ายหรือไม่ จาก stress_q3",
    )
    triage_classification: Optional[str] = Field(
        default=None,
        description="'red' ถ้า stress triage ระบุว่าเป็นกรณีวิกฤต, None ถ้าไม่ใช่",
    )
    advance_to_debt_inventory: bool = Field(
        default=False,
        description="True เมื่อ Phase 1 เสร็จสิ้นและควรเข้า Phase 2",
    )


class WelcomeNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str, langfuse_prompt=None) -> None:
        structured_llm = llm.with_structured_output(WelcomeOutput)
        metadata = {"langfuse_prompt": langfuse_prompt} if langfuse_prompt else {}
        prompt = ChatPromptTemplate(
            [("system", system_prompt), ("placeholder", "{messages}")],
            metadata=metadata,
        )
        self._chain = prompt | structured_llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        journey_step = state.get("journey_step") or ""

        try:
            output: WelcomeOutput = self._chain.invoke(
                {
                    "messages": state["messages"],
                    "journey_step": journey_step,
                },
                config=config,
            )
        except Exception as exc:
            logger.warning("WelcomeNode failed (%s) — returning safe fallback", exc)
            return {
                "messages": [
                    AIMessage(
                        content="สวัสดีค่ะ ยินดีต้อนรับสู่ MoneyThunder ดิฉันพร้อมช่วยเรื่องหนี้สินของคุณค่ะ กรุณาลองใหม่อีกครั้งนะคะ"
                    )
                ],
            }

        result: dict = {
            "messages": [AIMessage(content=output.message)],
            "journey_step": output.next_step,
        }

        # Conditionally update PDPA consent
        if output.pdpa_consented is not None:
            result["pdpa_consented"] = output.pdpa_consented

        # Merge stress triage answers into existing dict
        existing_triage = state.get("stress_triage") or {}
        triage_updated = False

        if output.num_creditors is not None:
            existing_triage["num_creditors"] = output.num_creditors
            triage_updated = True

        if output.missing_payments is not None:
            existing_triage["missing_payments"] = output.missing_payments
            triage_updated = True

        if output.income_covers_bills is not None:
            existing_triage["income_covers_bills"] = output.income_covers_bills
            triage_updated = True

        if triage_updated:
            result["stress_triage"] = existing_triage

        # Triage classification
        if output.triage_classification is not None:
            result["triage_classification"] = output.triage_classification

        # Advance to Phase 2: Debt Inventory
        if output.advance_to_debt_inventory:
            result["journey_phase"] = "debt_inventory"
            result["journey_step"] = ""

        return result
