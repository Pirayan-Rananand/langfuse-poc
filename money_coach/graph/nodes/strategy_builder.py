from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from money_coach.state import State


def _format_financial_context(state: State) -> str:
    """Build a SystemMessage string with all financial context for the strategy agent."""
    debts = state.get("debt_inventory", [])
    cf = state.get("cash_flow_data", {})
    summary = state.get("financial_summary", {})
    classification = state.get("triage_classification", "unknown")

    debt_lines = "\n".join(
        f"  - {d.get('creditor', '?')}: ยอดคงเหลือ {d.get('outstanding_balance', '?')} บาท, "
        f"ดอกเบี้ย {d.get('annual_interest_rate', '?')}%/ปี, "
        f"ขั้นต่ำ {d.get('minimum_monthly_payment', '?')} บาท"
        + (" [ค้างชำระ]" if d.get("is_overdue") else "")
        for d in debts
    ) or "  ไม่มีข้อมูลหนี้"

    return (
        f"[ข้อมูลการเงินของผู้ใช้]\n"
        f"ระดับความเสี่ยง: {classification.upper()}\n"
        f"DTI Ratio: {summary.get('dti_ratio', 'N/A')}%\n"
        f"Net Cash Flow: {summary.get('net_cash_flow', 'N/A')} บาท/เดือน\n"
        f"รายได้: {cf.get('monthly_income', 'N/A')} บาท/เดือน\n"
        f"รายจ่ายคงที่: {cf.get('fixed_expenses', 'N/A')} บาท\n"
        f"รายจ่ายผันแปร: {cf.get('variable_expenses', 'N/A')} บาท\n"
        f"หนี้ทั้งหมด ({len(debts)} ราย):\n{debt_lines}\n"
        f"ยอดหนี้รวม: {summary.get('total_debt', 'N/A')} บาท\n"
        f"ยอดชำระขั้นต่ำรวม: {summary.get('total_min_payments', 'N/A')} บาท/เดือน"
    )


class StrategyBuilderNode:
    """ReAct agent node that builds a debt payoff strategy.

    Wraps a `create_react_agent` graph (passed in as *strategy_graph*)
    with the same pattern used by CoachNode: inject financial context
    as a leading SystemMessage, invoke the agent, and return its messages.
    """

    def __init__(self, strategy_graph) -> None:
        self._graph = strategy_graph

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        messages = list(state["messages"])

        # Inject financial context so the agent has full visibility
        context = _format_financial_context(state)
        messages = [SystemMessage(content=context)] + messages

        result = self._graph.invoke({"messages": messages}, config=config)
        return {"messages": result["messages"]}
