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
        disable_streaming=True,
    )


def build_graph(config: AppConfig, checkpointer=None):
    eg_text, eg_prompt = fetch_prompt(
        "money-coach-emotional-gate",
        fallback=config.agents.emotional_gate.prompts.instruction,
    )
    emotional_gate_node = EmotionalGateNode(
        llm=_make_llm(config.agents.emotional_gate.model),
        system_prompt=eg_text,
        langfuse_prompt=eg_prompt,
    )

    comfort_text, comfort_prompt = fetch_prompt(
        "money-coach-comfort",
        fallback=config.agents.comfort.prompts.instruction,
    )
    comfort_node = ComfortNode(
        llm=_make_llm(config.agents.comfort.model),
        system_prompt=comfort_text,
        langfuse_prompt=comfort_prompt,
    )

    assessment_text, assessment_prompt = fetch_prompt(
        "money-coach-assessment",
        fallback=config.agents.assessment.prompts.instruction,
    )
    assessment_node = AssessmentNode(
        llm=_make_llm(config.agents.assessment.model),
        system_prompt=assessment_text,
        langfuse_prompt=assessment_prompt,
    )

    classifier_text, classifier_prompt = fetch_prompt(
        "money-coach-classifier",
        fallback=config.agents.classifier.prompts.instruction,
    )
    classifier_node = ClassifierNode(
        llm=_make_llm(config.agents.classifier.model),
        system_prompt=classifier_text,
        langfuse_prompt=classifier_prompt,
    )

    escalate_node = EscalateNode()

    main_text, main_prompt = fetch_prompt(
        "money-coach-main",
        fallback=config.agents.main.prompts.instruction,
    )
    coach_prompt_template = ChatPromptTemplate(
        [("system", main_text), ("placeholder", "{messages}")],
        metadata={"langfuse_prompt": main_prompt} if main_prompt else {},
    )
    coach_node = CoachNode(
        coach_graph=create_react_agent(
            model=_make_llm(config.agents.main.model),
            tools=_TOOLS,
            prompt=coach_prompt_template,
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
