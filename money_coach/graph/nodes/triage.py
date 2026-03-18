import logging

from langchain_core.runnables import RunnableConfig

from money_coach.state import State

logger = logging.getLogger(__name__)


class TriageNode:
    """Pure computation node — classifies debt severity from cash flow and debt data.

    No LLM required. Computes DTI ratio, net cash flow, and assigns a
    triage classification: green / yellow / orange / red.
    """

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        cf = state.get("cash_flow_data") or {}
        debts = state.get("debt_inventory") or []

        income = cf.get("monthly_income", 0) or 0
        fixed = cf.get("fixed_expenses", 0) or 0
        variable = cf.get("variable_expenses", 0) or 0

        total_min = sum(d.get("minimum_monthly_payment", 0) or 0 for d in debts)
        dti = total_min / income * 100 if income > 0 else 999
        net_cf = income - fixed - variable - total_min

        # Classification thresholds
        if fixed + variable + total_min > income:
            classification = "red"
        elif dti > 70:
            classification = "orange"
        elif dti > 50:
            classification = "yellow"
        else:
            classification = "green"

        logger.info(
            "TriageNode: dti=%.1f%%, net_cf=%.2f, classification=%s",
            dti,
            net_cf,
            classification,
        )

        return {
            "triage_classification": classification,
            "financial_summary": {
                "net_cash_flow": round(net_cf, 2),
                "dti_ratio": round(dti, 1),
                "total_debt": sum(d.get("outstanding_balance", 0) or 0 for d in debts),
                "num_creditors": len(debts),
                "total_min_payments": round(total_min, 2),
            },
            "journey_phase": "strategy" if classification != "red" else state.get("journey_phase", "cash_flow"),
            "journey_step": "",
        }
