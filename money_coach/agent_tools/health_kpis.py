from __future__ import annotations

from langchain_core.tools import tool


@tool
def negative_amortization_check(
    balance: float, annual_rate: float, min_payment: float
) -> dict:
    """Check if a debt has negative amortization (min payment < monthly interest).

    Negative amortization occurs when the minimum payment does not cover
    the monthly interest, causing the outstanding balance to grow over time.

    Args:
        balance: Current outstanding balance in dollars.
        annual_rate: Annual interest rate as a percentage (e.g. 18.0 for 18%).
        min_payment: Monthly minimum payment in dollars.

    Returns:
        Dict with is_negative_amort, monthly_interest, shortfall, and warning.
    """
    if balance <= 0:
        return {
            "is_negative_amort": False,
            "monthly_interest": 0.0,
            "shortfall": 0.0,
            "warning": "Balance is zero or negative — no amortization issue.",
        }

    if annual_rate <= 0:
        return {
            "is_negative_amort": False,
            "monthly_interest": 0.0,
            "shortfall": 0.0,
            "warning": "Interest rate is zero or negative — no amortization issue.",
        }

    monthly_rate = annual_rate / 100.0 / 12.0
    monthly_interest = balance * monthly_rate
    shortfall = max(0.0, monthly_interest - min_payment)
    is_negative = min_payment < monthly_interest

    if is_negative:
        warning = (
            f"Negative amortization detected: minimum payment ({min_payment:.2f}) "
            f"is less than monthly interest ({monthly_interest:.2f}). "
            f"The balance will grow by approximately {shortfall:.2f}/month. "
            f"You need to pay at least {monthly_interest:.2f}/month to stop "
            f"the balance from increasing."
        )
    else:
        principal_portion = min_payment - monthly_interest
        warning = (
            f"No negative amortization. Payment ({min_payment:.2f}) covers "
            f"monthly interest ({monthly_interest:.2f}) with {principal_portion:.2f} "
            f"going toward principal reduction."
        )

    return {
        "is_negative_amort": is_negative,
        "monthly_interest": round(monthly_interest, 2),
        "shortfall": round(shortfall, 2),
        "warning": warning,
    }


def _traffic_light(metric: str, value: float) -> dict:
    """Return traffic-light status for a given KPI metric and value.

    Thresholds follow the PRD definitions:
        - net_cash_flow: green >= 0, red < 0
        - dti_ratio: green <= 50%, yellow <= 70%, orange > 70%
        - savings_rate: green >= 20%, yellow >= 10%, orange < 10%
        - emergency_fund_months: green >= 3, yellow >= 1, orange < 1
    """
    if metric == "net_cash_flow":
        if value >= 0:
            return {"status": "green", "label": "Positive"}
        return {"status": "red", "label": "Negative"}

    if metric == "dti_ratio":
        if value <= 50:
            return {"status": "green", "label": "Manageable"}
        if value <= 70:
            return {"status": "yellow", "label": "Elevated"}
        return {"status": "orange", "label": "High Risk"}

    if metric == "savings_rate":
        if value >= 20:
            return {"status": "green", "label": "Healthy"}
        if value >= 10:
            return {"status": "yellow", "label": "Below Target"}
        return {"status": "orange", "label": "Insufficient"}

    if metric == "emergency_fund_months":
        if value >= 3:
            return {"status": "green", "label": "Adequate"}
        if value >= 1:
            return {"status": "yellow", "label": "Low"}
        return {"status": "orange", "label": "Critical"}

    return {"status": "unknown", "label": "Unknown metric"}


@tool
def financial_health_kpi(
    income: float,
    fixed_expenses: float,
    variable_expenses: float,
    savings: float,
    total_min_payments: float,
) -> dict:
    """Compute all 4 PRD financial health KPIs with traffic-light status.

    The four KPIs are:
        1. Net Cash Flow: income - (fixed + variable expenses + debt payments)
        2. DTI Ratio: (total_min_payments / income) * 100
        3. Savings Rate: (savings / income) * 100
        4. Emergency Fund Coverage: savings / (fixed + variable expenses) in months

    Args:
        income: Total monthly gross income in dollars.
        fixed_expenses: Monthly fixed expenses (rent, insurance, subscriptions).
        variable_expenses: Monthly variable expenses (food, transport, entertainment).
        savings: Current total liquid savings balance in dollars.
        total_min_payments: Total monthly minimum debt payments across all debts.

    Returns:
        Dict with each KPI value, traffic-light status, and an overall summary.
    """
    if income <= 0:
        return {"error": "Income must be positive"}

    total_expenses = fixed_expenses + variable_expenses
    monthly_outflow = total_expenses + total_min_payments

    # KPI 1: Net Cash Flow
    net_cash_flow = income - monthly_outflow
    net_cash_flow_pct = (net_cash_flow / income) * 100

    # KPI 2: DTI Ratio
    dti_ratio = (total_min_payments / income) * 100

    # KPI 3: Savings Rate (savings as % of income — monthly savings contribution
    # approximated as net cash flow if positive, else 0)
    monthly_savings_capacity = max(0.0, net_cash_flow)
    savings_rate = (monthly_savings_capacity / income) * 100

    # KPI 4: Emergency Fund Coverage (months of essential expenses covered)
    if total_expenses > 0:
        emergency_fund_months = savings / total_expenses
    else:
        emergency_fund_months = float("inf") if savings > 0 else 0.0

    # Traffic-light assessments
    kpis = {
        "net_cash_flow": {
            "value": round(net_cash_flow, 2),
            "pct_of_income": round(net_cash_flow_pct, 1),
            **_traffic_light("net_cash_flow", net_cash_flow),
        },
        "dti_ratio": {
            "value": round(dti_ratio, 1),
            **_traffic_light("dti_ratio", dti_ratio),
        },
        "savings_rate": {
            "value": round(savings_rate, 1),
            "monthly_savings_capacity": round(monthly_savings_capacity, 2),
            **_traffic_light("savings_rate", savings_rate),
        },
        "emergency_fund_months": {
            "value": round(emergency_fund_months, 1),
            "current_savings": round(savings, 2),
            "monthly_essential_expenses": round(total_expenses, 2),
            **_traffic_light("emergency_fund_months", emergency_fund_months),
        },
    }

    # Overall health: worst traffic light across all KPIs
    priority = {"orange": 0, "red": 0, "yellow": 1, "green": 2, "unknown": -1}
    worst = min(
        (kpi["status"] for kpi in kpis.values()),
        key=lambda s: priority.get(s, -1),
    )

    return {
        "income": round(income, 2),
        "total_expenses": round(total_expenses, 2),
        "total_min_payments": round(total_min_payments, 2),
        "kpis": kpis,
        "overall_status": worst,
        "summary": _build_summary(kpis, worst),
    }


def _build_summary(kpis: dict, overall_status: str) -> str:
    """Build a human-readable summary of all KPIs."""
    lines = []

    ncf = kpis["net_cash_flow"]
    if ncf["status"] == "green":
        lines.append(
            f"Net cash flow is positive ({ncf['value']:+,.2f}/month, "
            f"{ncf['pct_of_income']}% of income)."
        )
    else:
        lines.append(
            f"Net cash flow is NEGATIVE ({ncf['value']:+,.2f}/month). "
            f"Spending exceeds income."
        )

    dti = kpis["dti_ratio"]
    lines.append(f"DTI ratio is {dti['value']}% ({dti['label']}).")

    sr = kpis["savings_rate"]
    lines.append(f"Savings rate is {sr['value']}% ({sr['label']}).")

    ef = kpis["emergency_fund_months"]
    if ef["value"] == float("inf"):
        lines.append("Emergency fund coverage: unlimited (no essential expenses).")
    else:
        lines.append(
            f"Emergency fund covers {ef['value']:.1f} months of expenses ({ef['label']})."
        )

    status_advice = {
        "green": "Overall financial health is good. Keep building toward your goals.",
        "yellow": "Some areas need attention. Focus on the yellow-flagged KPIs.",
        "orange": "Financial health needs urgent attention. Address orange-flagged KPIs first.",
        "red": "Critical financial situation. Seek professional guidance immediately.",
    }
    lines.append(status_advice.get(overall_status, ""))

    return " ".join(lines)
