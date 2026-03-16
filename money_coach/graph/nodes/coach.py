from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from money_coach.state import State


def _format_assessment_context(assessment_data: dict, debt_case: str) -> str:
    debts = assessment_data.get("debts") or []
    debt_lines = "\n".join(
        f"  - {d.get('creditor', '?')}: ยอด {d.get('balance', '?')} บาท, "
        f"ดอกเบี้ย {d.get('annual_interest_rate', '?')}%/ปี, "
        f"ขั้นต่ำ {d.get('min_payment', '?')} บาท"
        + (" [ค้างชำระ]" if d.get("is_overdue") else "")
        for d in debts
    ) or "  ไม่มีข้อมูลหนี้"

    return (
        f"[ข้อมูลการประเมินทางการเงินของผู้ใช้]\n"
        f"ประเภทเคส: {debt_case.upper()}\n"
        f"รายได้ต่อเดือน: {assessment_data.get('monthly_income', 'ไม่ระบุ')} บาท\n"
        f"รายจ่ายคงที่: {assessment_data.get('fixed_expenses', 'ไม่ระบุ')} บาท\n"
        f"รายจ่ายผันแปร: {assessment_data.get('variable_expenses', 'ไม่ระบุ')} บาท\n"
        f"หนี้:\n{debt_lines}\n"
        f"เงินออม: {assessment_data.get('savings_balance', 'ไม่ระบุ')} บาท\n"
        f"ค้างชำระ: {assessment_data.get('is_missing_payments', 'ไม่ระบุ')}"
    )


class CoachNode:
    def __init__(self, coach_graph) -> None:
        self._graph = coach_graph

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        messages = list(state["messages"])
        assessment_data = state.get("assessment_data") or {}
        debt_case = state.get("debt_case", "unknown")

        if assessment_data:
            context = _format_assessment_context(assessment_data, debt_case)
            messages = [SystemMessage(content=context)] + messages

        result = self._graph.invoke({"messages": messages}, config=config)
        return {"messages": result["messages"]}
