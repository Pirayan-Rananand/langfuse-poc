"""Money Coach LangGraph agent.

Exports `graph` for langgraph.json.

Flow: START → clarify → END  (asks follow-up questions when context is thin)
               ↓
             coach → END  (ReAct agent with financial tools)
"""

import os

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from money_coach.chains.clarifier import ClarifyNode, build_clarifier
from money_coach.configs import agent_config
from money_coach.configs.model import AppConfig
from money_coach.prompts import fetch_prompt
from money_coach.state import State
from money_coach.tools import (
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
)

load_dotenv()

_TOOLS = [
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
]


def _make_llm(model: str) -> ChatOpenAI:
    # Routes through OpenRouter's OpenAI-compatible endpoint
    return ChatOpenAI(
        model=model,
        temperature=0.3,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
    )


def build_graph(config: AppConfig):
    clarify_node = ClarifyNode(
        clarifier_chain=build_clarifier(
            llm=_make_llm(config.agents.clarifier.model),
            system_prompt=fetch_prompt(
                "money-coach-clarifier",
                fallback=config.agents.clarifier.prompts.instruction,
            ),
        )
    )
    coach_graph = create_react_agent(
        model=_make_llm(config.agents.main.model),
        tools=_TOOLS,
        prompt=fetch_prompt(
            "money-coach-main",
            fallback=config.agents.main.prompts.instruction,
        ),
    )

    def coach_node(state: State, config: RunnableConfig) -> dict:
        result = coach_graph.invoke({"messages": state["messages"]}, config=config)
        return {"messages": result["messages"]}

    def _route_after_clarify(state: State) -> str:
        return END if state.get("needs_clarification") else "coach"

    builder = StateGraph(State)
    builder.add_node("clarify", clarify_node)
    builder.add_node("coach", coach_node)
    builder.add_edge(START, "clarify")
    builder.add_conditional_edges("clarify", _route_after_clarify)
    builder.add_edge("coach", END)

    return builder.compile()


graph = build_graph(agent_config)
