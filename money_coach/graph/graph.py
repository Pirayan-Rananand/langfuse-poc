# Exports `graph` for langgraph.json.

import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from money_coach.configs import agent_config
from money_coach.configs.model import AppConfig
from money_coach.graph.nodes import (
    CashFlowNode,
    ComfortNode,
    DebtInventoryNode,
    EmotionalGateNode,
    EscalateNode,
    StrategyBuilderNode,
    TriageNode,
    WelcomeNode,
)
from money_coach.utils import fetch_prompt
from money_coach.state import State
from money_coach.agent_tools import (
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_health_kpi,
)

load_dotenv()

_STRATEGY_TOOLS = [
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_health_kpi,
]


def _make_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=0.3,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        disable_streaming=True,
    )


def build_graph(config: AppConfig, checkpointer=None):
    # --- Emotional Gate (kept) ---
    eg_text, eg_prompt = fetch_prompt(
        "money-coach-emotional-gate",
        fallback=config.agents.emotional_gate.prompts.instruction,
    )
    emotional_gate_node = EmotionalGateNode(
        llm=_make_llm(config.agents.emotional_gate.model),
        system_prompt=eg_text,
        langfuse_prompt=eg_prompt,
    )

    # --- Comfort (kept) ---
    comfort_text, comfort_prompt = fetch_prompt(
        "money-coach-comfort",
        fallback=config.agents.comfort.prompts.instruction,
    )
    comfort_node = ComfortNode(
        llm=_make_llm(config.agents.comfort.model),
        system_prompt=comfort_text,
        langfuse_prompt=comfort_prompt,
    )

    # --- Welcome (new — Phase 1) ---
    welcome_text, welcome_prompt = fetch_prompt(
        "money-coach-welcome",
        fallback=config.agents.welcome.prompts.instruction,
    )
    welcome_node = WelcomeNode(
        llm=_make_llm(config.agents.welcome.model),
        system_prompt=welcome_text,
        langfuse_prompt=welcome_prompt,
    )

    # --- Debt Inventory (new — Phase 2) ---
    di_text, di_prompt = fetch_prompt(
        "money-coach-debt-inventory",
        fallback=config.agents.debt_inventory.prompts.instruction,
    )
    debt_inventory_node = DebtInventoryNode(
        llm=_make_llm(config.agents.debt_inventory.model),
        system_prompt=di_text,
        langfuse_prompt=di_prompt,
    )

    # --- Cash Flow (new — Phase 3) ---
    cf_text, cf_prompt = fetch_prompt(
        "money-coach-cash-flow",
        fallback=config.agents.cash_flow.prompts.instruction,
    )
    cash_flow_node = CashFlowNode(
        llm=_make_llm(config.agents.cash_flow.model),
        system_prompt=cf_text,
        langfuse_prompt=cf_prompt,
    )

    # --- Triage (new — pure computation, replaces classifier) ---
    triage_node = TriageNode()

    # --- Escalate (updated) ---
    escalate_node = EscalateNode()

    # --- Strategy Builder (new — Phase 4, replaces coach) ---
    sb_text, sb_prompt = fetch_prompt(
        "money-coach-strategy-builder",
        fallback=config.agents.strategy_builder.prompts.instruction,
    )
    sb_prompt_template = ChatPromptTemplate(
        [("system", sb_text), ("placeholder", "{messages}")],
        metadata={"langfuse_prompt": sb_prompt} if sb_prompt else {},
    )
    strategy_builder_node = StrategyBuilderNode(
        strategy_graph=create_react_agent(
            model=_make_llm(config.agents.strategy_builder.model),
            tools=_STRATEGY_TOOLS,
            prompt=sb_prompt_template,
        )
    )

    # --- Routing functions ---

    def route_emotional(state: State) -> str:
        if state.get("emotional_state") == "distressed":
            return "comfort"
        return "phase_router"

    def route_phase(state: State) -> str:
        phase = state.get("journey_phase") or "welcome"
        if phase == "welcome":
            return "welcome"
        elif phase == "debt_inventory":
            return "debt_inventory"
        elif phase == "cash_flow":
            return "cash_flow"
        elif phase == "strategy":
            return "strategy_builder"
        return "welcome"  # fallback

    def route_welcome_result(state: State) -> str:
        if state.get("triage_classification") == "red":
            return "escalate"
        return END

    def route_cash_flow_result(state: State) -> str:
        if state.get("cash_flow_complete"):
            return "triage"
        return END

    def route_triage(state: State) -> str:
        if state.get("triage_classification") == "red":
            return "escalate"
        return END

    # --- Build graph ---

    builder = StateGraph(State)
    builder.add_node("emotional_gate", emotional_gate_node)
    builder.add_node("comfort", comfort_node)
    builder.add_node("welcome", welcome_node)
    builder.add_node("debt_inventory", debt_inventory_node)
    builder.add_node("cash_flow", cash_flow_node)
    builder.add_node("triage", triage_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("strategy_builder", strategy_builder_node)

    builder.add_edge(START, "emotional_gate")
    builder.add_conditional_edges(
        "emotional_gate",
        route_emotional,
        {"comfort": "comfort", "phase_router": "phase_router"},
    )

    # Phase router is a virtual node (conditional edges from emotional_gate)
    # We implement it as conditional edges using a routing node
    def _phase_router_noop(state: State, config):
        return {}

    builder.add_node("phase_router", _phase_router_noop)
    builder.add_conditional_edges(
        "phase_router",
        route_phase,
        {
            "welcome": "welcome",
            "debt_inventory": "debt_inventory",
            "cash_flow": "cash_flow",
            "strategy_builder": "strategy_builder",
        },
    )

    builder.add_edge("comfort", END)

    builder.add_conditional_edges(
        "welcome",
        route_welcome_result,
        {"escalate": "escalate", END: END},
    )

    builder.add_edge("debt_inventory", END)

    builder.add_conditional_edges(
        "cash_flow",
        route_cash_flow_result,
        {"triage": "triage", END: END},
    )

    builder.add_conditional_edges(
        "triage",
        route_triage,
        {"escalate": "escalate", END: END},
    )

    builder.add_edge("escalate", END)
    builder.add_edge("strategy_builder", END)

    return builder.compile(checkpointer=checkpointer)


def _with_session_callback(config: dict | None) -> dict:
    # Attach a Langfuse callback and map thread_id → session via metadata
    config = dict(config or {})
    thread_id = config.get("configurable", {}).get("thread_id")
    if thread_id:
        metadata = dict(config.get("metadata") or {})
        metadata["langfuse_session_id"] = (
            thread_id  # CallbackHandler reads ``langfuse_session_id`` from the LangChain run metadata and uses it as the Langfuse session_id for the trace
        )
        config["metadata"] = metadata
    config["callbacks"] = list(config.get("callbacks", [])) + [CallbackHandler()]
    return config


graph = build_graph(agent_config)


class _SessionGraph(type(graph)):
    def invoke(self, input, config=None, **kwargs):
        return super().invoke(input, _with_session_callback(config), **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        return await super().ainvoke(input, _with_session_callback(config), **kwargs)

    def astream(self, input, config=None, **kwargs):
        return super().astream(input, _with_session_callback(config), **kwargs)

    def astream_events(self, input, config=None, **kwargs):
        return super().astream_events(input, _with_session_callback(config), **kwargs)


graph.__class__ = _SessionGraph
