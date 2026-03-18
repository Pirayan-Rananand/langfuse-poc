from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    # Journey tracking
    journey_phase: str       # "welcome" | "debt_inventory" | "cash_flow" | "strategy"
    journey_step: str        # sub-step within phase

    # Phase 1: Welcome & Triage
    emotional_state: str     # "unknown" | "ready" | "distressed"
    pdpa_consented: bool
    stress_triage: dict      # {num_creditors, missing_payments, income_covers_bills}

    # Phase 2: Debt Inventory
    debt_inventory: list     # list of DebtItem dicts
    debt_inventory_complete: bool

    # Phase 3: Cash Flow
    cash_flow_data: dict     # {monthly_income, fixed_expenses, variable_expenses, desired_monthly_savings}
    cash_flow_complete: bool

    # Triage
    triage_classification: str   # "green" | "yellow" | "orange" | "red"
    financial_summary: dict      # {net_cash_flow, dti_ratio, total_debt, total_min_payments, ...}

    # Phase 4: Strategy
    selected_strategy: str       # "snowball" | "avalanche" | ""
    payoff_plan: dict            # {schedule, projected_debt_free_date, total_interest, ...}
    plan_confirmed: bool
