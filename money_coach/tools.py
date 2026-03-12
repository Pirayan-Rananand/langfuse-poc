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


@tool
def debt_payoff_calculator(
    debts: list,
    strategy: str = "avalanche",
    extra_monthly: float = 0.0,
) -> dict:
    """Calculate debt payoff schedule using snowball or avalanche strategy.

    Args:
        debts: List of dicts, each with keys: name (str), balance (float),
               apr (float, annual %), min_payment (float).
        strategy: "avalanche" (highest APR first, minimizes interest) or
                  "snowball" (lowest balance first, maximizes motivation).
        extra_monthly: Extra dollars applied to the target debt each month beyond minimums.

    Returns:
        Dict with months_to_debt_free, total_interest_paid, total_paid, and per-debt schedule.
    """
    import copy

    if not debts:
        return {"error": "No debts provided"}

    debts_state = copy.deepcopy(debts)
    for d in debts_state:
        d["balance"] = float(d["balance"])
        d["apr"] = float(d["apr"])
        d["min_payment"] = float(d["min_payment"])
        d["total_interest"] = 0.0
        d["months"] = 0

    if strategy == "snowball":
        priority_key = lambda d: d["balance"]
    else:  # avalanche (default)
        priority_key = lambda d: -d["apr"]

    month = 0
    total_interest = 0.0
    total_paid = 0.0
    max_months = 600  # 50-year safety cap

    while any(d["balance"] > 0 for d in debts_state) and month < max_months:
        month += 1
        active = [d for d in debts_state if d["balance"] > 0]
        active.sort(key=priority_key)

        # Apply minimum payments to all debts
        for d in active:
            monthly_rate = d["apr"] / 100 / 12
            interest = d["balance"] * monthly_rate
            d["total_interest"] += interest
            total_interest += interest

            payment = min(d["min_payment"], d["balance"] + interest)
            d["balance"] = max(0.0, d["balance"] + interest - payment)
            total_paid += payment
            d["months"] = month

        # Apply extra payment to highest-priority active debt
        remaining_extra = extra_monthly
        for d in active:
            if d["balance"] <= 0:
                continue
            extra_applied = min(remaining_extra, d["balance"])
            d["balance"] = max(0.0, d["balance"] - extra_applied)
            total_paid += extra_applied
            remaining_extra -= extra_applied
            if remaining_extra <= 0:
                break

    schedule = [
        {
            "name": d["name"],
            "original_balance": debts[i]["balance"],
            "total_interest_paid": round(d["total_interest"], 2),
            "months_to_payoff": d["months"],
        }
        for i, d in enumerate(debts_state)
    ]

    return {
        "strategy": strategy,
        "months_to_debt_free": month,
        "years_to_debt_free": round(month / 12, 1),
        "total_interest_paid": round(total_interest, 2),
        "total_paid": round(total_paid, 2),
        "per_debt_schedule": schedule,
    }


@tool
def dti_ratio_calculator(
    monthly_gross_income: float, monthly_debt_payments: float
) -> dict:
    """Calculate debt-to-income (DTI) ratio and risk level.

    Args:
        monthly_gross_income: Gross (pre-tax) monthly income in dollars.
        monthly_debt_payments: Total monthly minimum debt payments (mortgage/rent, loans, credit cards).

    Returns:
        Dict with dti_pct, risk_level, and guidance.
    """
    if monthly_gross_income <= 0:
        return {"error": "Monthly gross income must be positive"}

    dti = monthly_debt_payments / monthly_gross_income * 100

    if dti <= 20:
        risk_level = "excellent"
        guidance = "Your DTI is excellent. Lenders view you as low risk."
    elif dti <= 36:
        risk_level = "good"
        guidance = "Your DTI is within the standard mortgage qualification range."
    elif dti <= 43:
        risk_level = "acceptable"
        guidance = "Borderline for most lenders. Focus on paying down debts."
    elif dti <= 50:
        risk_level = "high"
        guidance = "High DTI. Many lenders will decline. Prioritize debt reduction."
    else:
        risk_level = "critical"
        guidance = (
            "Critical DTI. Seek financial counseling and aggressively reduce debt."
        )

    return {
        "monthly_gross_income": monthly_gross_income,
        "monthly_debt_payments": monthly_debt_payments,
        "dti_pct": round(dti, 1),
        "risk_level": risk_level,
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
                "Track every dollar – awareness precedes change",
                "Pay yourself first by automating savings transfers",
            ],
            "action_steps": [
                "List all income sources and fixed expenses",
                "Categorize discretionary spending for the last 3 months",
                "Set spending limits per category and review weekly",
                "Use the budget_calculator tool to see your current surplus/deficit",
            ],
            "warnings": [
                "Lifestyle inflation erodes raises – keep expenses flat as income grows",
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
                "Length of credit history matters – keep old accounts open",
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
                "Target 3–6 months of essential expenses in liquid savings",
                "Keep emergency fund in a high-yield savings account (HYSA)",
                "Build $1,000 starter fund before aggressively paying debt",
            ],
            "action_steps": [
                "Calculate monthly essential expenses (rent, food, utilities, minimums)",
                "Open a separate HYSA so the funds are not tempting to spend",
                "Automate a fixed weekly transfer until the target is reached",
            ],
            "warnings": [
                "Do not invest emergency funds – liquidity is the priority",
                "Replenish the fund immediately after any emergency withdrawal",
            ],
        },
        "investing": {
            "key_principles": [
                "Eliminate high-interest debt (>7% APR) before investing",
                "Capture employer 401k match first – it is a guaranteed 50–100% return",
                "Low-cost index funds beat most active managers over long horizons",
            ],
            "action_steps": [
                "Contribute enough to 401k to get full employer match",
                "Max Roth IRA ($7,000/year in 2025) for tax-free growth",
                "Invest in broad market index funds (e.g. VTI, VXUS)",
            ],
            "warnings": [
                "Do not invest money you will need in the next 3–5 years",
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
