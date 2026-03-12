"""Money Coach LangGraph agent.

Exports `graph` – the LangGraph target referenced in langgraph.json.

Graph flow:
    START → clarify → (needs clarification?) → END   (returns questions to user)
                    → coach                  → END   (runs ReAct agent with tools)
"""

import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from money_coach.agents.clarifier import build_clarifier
from money_coach.configs import agent_config
from money_coach.tools import (
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
)

load_dotenv()


# ── Shared state ──────────────────────────────────────────────────────────────


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    needs_clarification: bool


# ── LLM factory (shared base, both agents use the same provider) ──────────────


def _make_llm(model_override: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=agent_config.agents.main.model,
        temperature=0.3,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
    )


# ── Clarifier agent ───────────────────────────────────────────────────────────

_clarifier_chain = build_clarifier(
    llm=_make_llm(),
    system_prompt=agent_config.agents.clarifier.prompts.instruction,
)


def clarify_node(state: State, config: RunnableConfig) -> dict:
    """Decide whether the user has provided enough context.

    If not, generate targeted follow-up questions and mark the state so the
    graph routes to END instead of the coach.

    Falls back to routing straight to the coach if the clarifier fails (e.g.
    the model returns malformed JSON) — never blocks the user.
    """
    try:
        decision = _clarifier_chain.invoke(
            {"messages": state["messages"]}, config=config
        )
    except Exception:
        return {"needs_clarification": False}

    if decision.needs_clarification:
        questions = "\n".join(f"- {q}" for q in decision.questions)
        reply = f"Before I can give you accurate advice, I need a bit more detail:\n\n{questions}"
        return {
            "messages": [AIMessage(content=reply)],
            "needs_clarification": True,
        }

    return {"needs_clarification": False}


# ── Coach agent (ReAct with financial tools) ──────────────────────────────────

_tools = [
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
]

_coach_graph = create_react_agent(
    model=_make_llm(),
    tools=_tools,
    prompt=agent_config.agents.main.prompts.instruction,
)


def coach_node(state: State, config: RunnableConfig) -> dict:
    """Run the ReAct coach and append its messages to the shared state."""
    result = _coach_graph.invoke({"messages": state["messages"]}, config=config)
    return {"messages": result["messages"]}


# ── Graph assembly ────────────────────────────────────────────────────────────


def _route_after_clarify(state: State) -> str:
    return END if state.get("needs_clarification") else "coach"


builder = StateGraph(State)
builder.add_node("clarify", clarify_node)
builder.add_node("coach", coach_node)

builder.add_edge(START, "clarify")
builder.add_conditional_edges("clarify", _route_after_clarify)
builder.add_edge("coach", END)

graph = builder.compile()
