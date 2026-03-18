from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta

from langchain_core.tools import tool


@tool
def budget_calculator(income: float, expenses: dict) -> dict:
    """Calculate monthly budget surplus or deficit given income and expense categories.

    Args:
        income: Total monthly take-home income in dollars.
        expenses: Dict mapping expense category names to monthly amounts (e.g. {"rent": 1200, "food": 400}).

    Returns:
        Dict with total_expenses, surplus_deficit, status, and per-category breakdown.
    """
    total_expenses = sum(expenses.values())
    surplus_deficit = income - total_expenses
    status = "surplus" if surplus_deficit >= 0 else "deficit"

    breakdown = {
        category: {
            "amount": amount,
            "pct_of_income": round(amount / income * 100, 1) if income > 0 else 0,
        }
        for category, amount in expenses.items()
    }

    return {
        "income": income,
        "total_expenses": total_expenses,
        "surplus_deficit": surplus_deficit,
        "status": status,
        "expense_ratio_pct": (
            round(total_expenses / income * 100, 1) if income > 0 else 0
        ),
        "breakdown": breakdown,
    }


def _theoretical_months(balance: float, annual_rate: float, payment: float) -> float | None:
    """Compute theoretical payoff months using the PRD formula.

    Formula: n = -ln(1 - (P*r)/M) / ln(1+r)
    where P = balance, r = monthly rate, M = monthly payment.

    Returns None if the payment is insufficient to cover monthly interest
    (negative amortization).
    """
    if balance <= 0:
        return 0.0
    if annual_rate <= 0:
        # Zero-interest: simple division
        return math.ceil(balance / payment) if payment > 0 else None

    r = annual_rate / 100.0 / 12.0
    monthly_interest = balance * r

    if payment <= monthly_interest:
        return None  # Negative amortization — payment never covers principal

    numerator = -math.log(1.0 - (balance * r) / payment)
    denominator = math.log(1.0 + r)
    return numerator / denominator


def _check_negative_amortization(
    debt_name: str, balance: float, annual_rate: float, min_payment: float
) -> dict | None:
    """Return a warning dict if min_payment < monthly interest, else None."""
    if balance <= 0 or annual_rate <= 0:
        return None
    monthly_interest = balance * (annual_rate / 100.0 / 12.0)
    if min_payment < monthly_interest:
        return {
            "debt_name": debt_name,
            "monthly_interest": round(monthly_interest, 2),
            "min_payment": round(min_payment, 2),
            "shortfall": round(monthly_interest - min_payment, 2),
            "warning": (
                f"Negative amortization on '{debt_name}': minimum payment "
                f"({min_payment:.2f}) is less than monthly interest "
                f"({monthly_interest:.2f}). Balance will grow over time."
            ),
        }
    return None


def _projected_debt_free_date(months_from_now: int) -> str:
    """Return a month/year string relative to today."""
    target = datetime.now() + timedelta(days=months_from_now * 30.44)
    return target.strftime("%B %Y")


def _simulate_strategy(
    debts: list[dict],
    strategy: str,
    extra_monthly: float,
    max_months: int = 600,
) -> dict:
    """Run a month-by-month debt payoff simulation for a single strategy.

    Returns the full result dict including schedule, totals, and warnings.
    """
    debts_state = copy.deepcopy(debts)
    for d in debts_state:
        d["balance"] = float(d["balance"])
        d["apr"] = float(d["apr"])
        d["min_payment"] = float(d["min_payment"])
        d["total_interest"] = 0.0
        d["total_paid"] = 0.0
        d["months"] = 0

    def _snowball_key(d):
        return d["balance"]

    def _avalanche_key(d):
        return -d["apr"]

    priority_key = _snowball_key if strategy == "snowball" else _avalanche_key

    # Pre-check for negative amortization
    neg_amort_warnings: list[dict] = []
    for d in debts_state:
        warn = _check_negative_amortization(
            d["name"], d["balance"], d["apr"], d["min_payment"]
        )
        if warn:
            neg_amort_warnings.append(warn)

    # Compute theoretical months per debt (standalone, ignoring cascade)
    theoretical: dict[str, float | None] = {}
    for d in debts_state:
        theoretical[d["name"]] = _theoretical_months(
            d["balance"], d["apr"], d["min_payment"]
        )

    month = 0
    total_interest = 0.0
    total_paid = 0.0
    monthly_schedule: list[dict] = []

    while any(d["balance"] > 0 for d in debts_state) and month < max_months:
        month += 1
        active = [d for d in debts_state if d["balance"] > 0]
        active.sort(key=priority_key)

        # Collect freed payments from debts paid off this round or earlier
        freed_payment = sum(
            d["min_payment"] for d in debts_state if d["balance"] <= 0
        )

        # Apply minimum payments to all active debts
        for d in active:
            monthly_rate = d["apr"] / 100.0 / 12.0
            interest = d["balance"] * monthly_rate
            d["total_interest"] += interest
            total_interest += interest

            payment = min(d["min_payment"], d["balance"] + interest)
            d["balance"] = max(0.0, d["balance"] + interest - payment)
            d["total_paid"] += payment
            total_paid += payment
            d["months"] = month

            monthly_schedule.append({
                "month": month,
                "debt_name": d["name"],
                "payment": round(payment, 2),
                "interest_paid": round(interest, 2),
                "remaining_balance": round(d["balance"], 2),
            })

        # Cascade: apply freed payments + extra to highest-priority active debt
        remaining_extra = extra_monthly + freed_payment
        for d in active:
            if d["balance"] <= 0 or remaining_extra <= 0:
                continue
            extra_applied = min(remaining_extra, d["balance"])
            d["balance"] = max(0.0, d["balance"] - extra_applied)
            d["total_paid"] += extra_applied
            total_paid += extra_applied
            remaining_extra -= extra_applied

            # Record the extra payment in the schedule
            if extra_applied > 0:
                monthly_schedule.append({
                    "month": month,
                    "debt_name": d["name"],
                    "payment": round(extra_applied, 2),
                    "interest_paid": 0.0,
                    "remaining_balance": round(d["balance"], 2),
                    "note": "cascade/extra payment",
                })

            if remaining_extra <= 0:
                break

    per_debt_schedule = [
        {
            "name": d["name"],
            "original_balance": debts[i]["balance"],
            "total_interest_paid": round(d["total_interest"], 2),
            "total_paid": round(d["total_paid"], 2),
            "months_to_payoff": d["months"],
            "theoretical_months_standalone": (
                round(theoretical[d["name"]], 1)
                if theoretical[d["name"]] is not None
                else None
            ),
        }
        for i, d in enumerate(debts_state)
    ]

    result: dict = {
        "strategy": strategy,
        "months_to_debt_free": month,
        "years_to_debt_free": round(month / 12, 1),
        "projected_debt_free_date": _projected_debt_free_date(month),
        "total_interest_paid": round(total_interest, 2),
        "total_paid": round(total_paid, 2),
        "per_debt_schedule": per_debt_schedule,
        "monthly_schedule": monthly_schedule,
    }

    if neg_amort_warnings:
        result["negative_amortization_warnings"] = neg_amort_warnings

    return result


@tool
def debt_payoff_calculator(
    debts: list,
    strategy: str = "avalanche",
    extra_monthly: float = 0.0,
) -> dict:
    """Calculate debt payoff schedule using snowball and avalanche strategies.

    Computes **both** snowball and avalanche projections regardless of the
    strategy parameter.  Includes month-by-month schedule, cascade logic
    (freed payments roll to the next priority debt), theoretical standalone
    payoff months per debt using the PRD formula, and negative amortization
    detection.

    Args:
        debts: List of dicts, each with keys: name (str), balance (float),
               apr (float, annual %), min_payment (float).
        strategy: "avalanche" or "snowball" — sets the recommended strategy
                  in the response, but both are always computed.
        extra_monthly: Extra dollars applied to the target debt each month
                       beyond minimums.

    Returns:
        Dict with recommended strategy result, both projections, and warnings.
    """
    if not debts:
        return {"error": "No debts provided"}

    # Validate and normalize inputs
    for d in debts:
        if float(d.get("balance", 0)) < 0:
            return {"error": f"Debt '{d.get('name', '?')}' has negative balance"}
        if float(d.get("apr", 0)) < 0:
            return {"error": f"Debt '{d.get('name', '?')}' has negative APR"}
        if float(d.get("min_payment", 0)) <= 0:
            return {"error": f"Debt '{d.get('name', '?')}' has non-positive min_payment"}

    avalanche_result = _simulate_strategy(debts, "avalanche", extra_monthly)
    snowball_result = _simulate_strategy(debts, "snowball", extra_monthly)

    # Determine recommended strategy (the one requested, default avalanche)
    recommended = strategy if strategy in ("avalanche", "snowball") else "avalanche"

    # Compute interest savings comparison
    interest_diff = abs(
        avalanche_result["total_interest_paid"]
        - snowball_result["total_interest_paid"]
    )
    if avalanche_result["total_interest_paid"] <= snowball_result["total_interest_paid"]:
        interest_savings_note = (
            f"Avalanche saves {interest_diff:.2f} in interest vs. snowball."
        )
    else:
        interest_savings_note = (
            f"Snowball saves {interest_diff:.2f} in interest vs. avalanche."
        )

    return {
        "recommended_strategy": recommended,
        "avalanche": avalanche_result,
        "snowball": snowball_result,
        "interest_comparison": interest_savings_note,
    }


@tool
def dti_ratio_calculator(
    monthly_gross_income: float, monthly_debt_payments: float
) -> dict:
    """Calculate debt-to-income (DTI) ratio and risk level using PRD thresholds.

    Thresholds:
        - Green (Manageable): DTI <= 50%
        - Yellow (Elevated):  50% < DTI <= 70%
        - Orange (High Risk): DTI > 70%

    Args:
        monthly_gross_income: Gross (pre-tax) monthly income in dollars.
        monthly_debt_payments: Total monthly minimum debt payments
            (mortgage/rent, loans, credit cards).

    Returns:
        Dict with dti_pct, risk_level, traffic_light, and guidance.
    """
    if monthly_gross_income <= 0:
        return {"error": "Monthly gross income must be positive"}

    dti = monthly_debt_payments / monthly_gross_income * 100

    if dti <= 50:
        risk_level = "manageable"
        traffic_light = "green"
        guidance = (
            "Your DTI is manageable. Continue making payments on time and "
            "consider accelerating debt payoff to build financial resilience."
        )
    elif dti <= 70:
        risk_level = "elevated"
        traffic_light = "yellow"
        guidance = (
            "Your DTI is elevated. Prioritize reducing high-interest debt, "
            "avoid taking on new obligations, and look for ways to increase "
            "income or cut discretionary spending."
        )
    else:
        risk_level = "high_risk"
        traffic_light = "orange"
        guidance = (
            "Your DTI is high risk. Seek professional financial counseling, "
            "consider debt consolidation or restructuring, and aggressively "
            "reduce expenses. Avoid any new borrowing."
        )

    return {
        "monthly_gross_income": monthly_gross_income,
        "monthly_debt_payments": monthly_debt_payments,
        "dti_pct": round(dti, 1),
        "risk_level": risk_level,
        "traffic_light": traffic_light,
        "guidance": guidance,
    }


@tool
def financial_advice_helper(topic: str, context: str = "") -> dict:
    """Provide structured guidance on common personal finance topics.

    Args:
        topic: One of: "budgeting", "debt", "credit", "emergency_fund", "investing".
        context: Optional user context to tailor advice (e.g. "I have $500/month free").

    Returns:
        Dict with key_principles, action_steps, and warnings.
    """
    topic_lower = topic.lower().strip()

    advice_db = {
        "budgeting": {
            "key_principles": [
                "50/30/20 rule: 50% needs, 30% wants, 20% savings/debt",
                "Track every dollar \u2013 awareness precedes change",
                "Pay yourself first by automating savings transfers",
            ],
            "action_steps": [
                "List all income sources and fixed expenses",
                "Categorize discretionary spending for the last 3 months",
                "Set spending limits per category and review weekly",
                "Use the budget_calculator tool to see your current surplus/deficit",
            ],
            "warnings": [
                "Lifestyle inflation erodes raises \u2013 keep expenses flat as income grows",
                "Irregular expenses (car repairs, medical) need a dedicated sinking fund",
            ],
        },
        "debt": {
            "key_principles": [
                "Avalanche saves the most money (target highest APR first)",
                "Snowball builds momentum (target lowest balance first)",
                "Always pay minimums on all debts to protect credit score",
            ],
            "action_steps": [
                "List all debts with balance, APR, and minimum payment",
                "Run debt_payoff_calculator to compare strategies",
                "Consider balance transfer to 0% APR card for high-interest credit card debt",
                "Negotiate lower interest rates with existing creditors",
            ],
            "warnings": [
                "Never take on new debt while aggressively paying down existing debt",
                "Debt consolidation loans only help if the APR is truly lower",
            ],
        },
        "credit": {
            "key_principles": [
                "Payment history (35%) and utilization (30%) drive your FICO score",
                "Keep credit card utilization below 30% (ideally below 10%)",
                "Length of credit history matters \u2013 keep old accounts open",
            ],
            "action_steps": [
                "Pull free credit reports from annualcreditreport.com",
                "Dispute any errors in writing with the credit bureau",
                "Set up autopay for minimums to eliminate missed payments",
                "Request credit limit increases to lower utilization ratio",
            ],
            "warnings": [
                "Hard inquiries stay on your report for 2 years",
                "Closing old cards can hurt your score by reducing available credit",
            ],
        },
        "emergency_fund": {
            "key_principles": [
                "Target 3\u20136 months of essential expenses in liquid savings",
                "Keep emergency fund in a high-yield savings account (HYSA)",
                "Build $1,000 starter fund before aggressively paying debt",
            ],
            "action_steps": [
                "Calculate monthly essential expenses (rent, food, utilities, minimums)",
                "Open a separate HYSA so the funds are not tempting to spend",
                "Automate a fixed weekly transfer until the target is reached",
            ],
            "warnings": [
                "Do not invest emergency funds \u2013 liquidity is the priority",
                "Replenish the fund immediately after any emergency withdrawal",
            ],
        },
        "investing": {
            "key_principles": [
                "Eliminate high-interest debt (>7% APR) before investing",
                "Capture employer 401k match first \u2013 it is a guaranteed 50\u2013100% return",
                "Low-cost index funds beat most active managers over long horizons",
            ],
            "action_steps": [
                "Contribute enough to 401k to get full employer match",
                "Max Roth IRA ($7,000/year in 2025) for tax-free growth",
                "Invest in broad market index funds (e.g. VTI, VXUS)",
            ],
            "warnings": [
                "Do not invest money you will need in the next 3\u20135 years",
                "Avoid individual stocks until you have a diversified core portfolio",
            ],
        },
    }

    if topic_lower not in advice_db:
        available = ", ".join(advice_db.keys())
        return {
            "error": f"Unknown topic '{topic}'. Available topics: {available}",
        }

    result = advice_db[topic_lower].copy()
    result["topic"] = topic_lower
    if context:
        result["context_note"] = f"Advice tailored with your context: {context}"
    return result
