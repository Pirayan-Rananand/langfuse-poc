# Exports `graph` for langgraph.json.

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from money_coach.configs import agent_config
from money_coach.configs.model import AppConfig
from money_coach.graph.nodes import (
    AssessmentNode,
    ClassifierNode,
    CoachNode,
    ComfortNode,
    EmotionalGateNode,
    EscalateNode,
)
from money_coach.utils import fetch_prompt
from money_coach.state import State
from money_coach.agent_tools import (
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
    return ChatOpenAI(
        model=model,
        temperature=0.3,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
    )


def build_graph(config: AppConfig, checkpointer=None):
    emotional_gate_node = EmotionalGateNode(
        llm=_make_llm(config.agents.emotional_gate.model),
        system_prompt=fetch_prompt(
            "money-coach-emotional-gate",
            fallback=config.agents.emotional_gate.prompts.instruction,
        ),
    )
    comfort_node = ComfortNode(
        llm=_make_llm(config.agents.comfort.model),
        system_prompt=fetch_prompt(
            "money-coach-comfort",
            fallback=config.agents.comfort.prompts.instruction,
        ),
    )
    assessment_node = AssessmentNode(
        llm=_make_llm(config.agents.assessment.model),
        system_prompt=fetch_prompt(
            "money-coach-assessment",
            fallback=config.agents.assessment.prompts.instruction,
        ),
    )
    classifier_node = ClassifierNode(
        llm=_make_llm(config.agents.classifier.model),
        system_prompt=fetch_prompt(
            "money-coach-classifier",
            fallback=config.agents.classifier.prompts.instruction,
        ),
    )
    escalate_node = EscalateNode()
    coach_node = CoachNode(
        coach_graph=create_react_agent(
            model=_make_llm(config.agents.main.model),
            tools=_TOOLS,
            prompt=fetch_prompt(
                "money-coach-main",
                fallback=config.agents.main.prompts.instruction,
            ),
        )
    )

    # --- routing functions ---

    def route_emotional(state: State) -> str:
        if state.get("emotional_state") == "distressed":
            return "comfort"
        if state.get("assessment_phase", "not_started") != "completed":
            return "assessment"
        if state.get("debt_case") == "red":
            return "escalate"
        return "coach"

    def route_assessment(state: State) -> str:
        return "classifier" if state.get("assessment_phase") == "completed" else END

    def route_case(state: State) -> str:
        return "escalate" if state.get("debt_case") == "red" else "coach"

    # --- build graph ---

    builder = StateGraph(State)
    builder.add_node("emotional_gate", emotional_gate_node)
    builder.add_node("comfort", comfort_node)
    builder.add_node("assessment", assessment_node)
    builder.add_node("classifier", classifier_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("coach", coach_node)

    builder.add_edge(START, "emotional_gate")
    builder.add_conditional_edges(
        "emotional_gate",
        route_emotional,
        {
            "comfort": "comfort",
            "assessment": "assessment",
            "escalate": "escalate",
            "coach": "coach",
        },
    )
    builder.add_edge("comfort", END)
    builder.add_conditional_edges(
        "assessment",
        route_assessment,
        {"classifier": "classifier", END: END},
    )
    builder.add_conditional_edges(
        "classifier",
        route_case,
        {"escalate": "escalate", "coach": "coach"},
    )
    builder.add_edge("escalate", END)
    builder.add_edge("coach", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_graph(agent_config).with_config({"callbacks": [CallbackHandler()]})
