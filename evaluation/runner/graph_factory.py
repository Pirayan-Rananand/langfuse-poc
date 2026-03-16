"""Build evaluation graphs with overridden prompt versions.

build_eval_graph wires the full money-coach graph but fetches prompts from
prod Langfuse, letting callers override specific prompt names with a fixed
version number (candidate) while the rest stay on fallback_label (baseline).
"""

import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from money_coach.agent_tools import (
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
)
from money_coach.configs.model import AppConfig
from money_coach.graph.nodes import (
    AssessmentNode,
    ClassifierNode,
    CoachNode,
    ComfortNode,
    EmotionalGateNode,
    EscalateNode,
)
from money_coach.state import State
from money_coach.utils.langfuse import fetch_prompt_by_label

logger = logging.getLogger(__name__)

_TOOLS = [
    budget_calculator,
    debt_payoff_calculator,
    dti_ratio_calculator,
    financial_advice_helper,
]


def _make_eval_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=0.3,
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        disable_streaming=True,
    )


def _resolve_prompt(
    prod_client: Langfuse,
    name: str,
    fallback: str,
    prompt_overrides: dict[str, int],
    fallback_label: str,
) -> tuple[str, object | None]:
    """Return (prompt_text, langfuse_prompt_obj).

    If `name` is in prompt_overrides, fetch that specific version from prod
    (candidate path).  Otherwise fetch by fallback_label (baseline path).
    """
    if name in prompt_overrides:
        version = prompt_overrides[name]
        try:
            p = prod_client.get_prompt(name, version=version)
            logger.debug("Loaded prompt '%s' v%s (candidate override)", name, version)
            return p.prompt, p
        except Exception as exc:
            logger.warning(
                "Could not fetch '%s' v%s: %s — using fallback text", name, version, exc
            )
            return fallback, None

    return fetch_prompt_by_label(prod_client, name, fallback_label, fallback)


def build_eval_graph(
    prod_client: Langfuse,
    app_config: AppConfig,
    prompt_overrides: dict[str, int] | None = None,
    fallback_label: str = "production",
):
    """Build the money-coach graph for evaluation.

    Args:
        prod_client: Langfuse client pointed at the prod project.
        app_config: AppConfig loaded from agents.yaml (provides fallback texts + models).
        prompt_overrides: {prompt_name: version_number} — these prompts are fetched
            by exact version (candidate).  All others use fallback_label.
        fallback_label: Langfuse label used for non-overridden prompts (default "production").
    """
    overrides = prompt_overrides or {}

    def _get(name: str, fallback: str) -> tuple[str, object | None]:
        return _resolve_prompt(prod_client, name, fallback, overrides, fallback_label)

    # --- build nodes ---

    eg_text, eg_prompt = _get(
        "money-coach-emotional-gate",
        app_config.agents.emotional_gate.prompts.instruction,
    )
    emotional_gate_node = EmotionalGateNode(
        llm=_make_eval_llm(app_config.agents.emotional_gate.model),
        system_prompt=eg_text,
        langfuse_prompt=eg_prompt,
    )

    comfort_text, comfort_prompt = _get(
        "money-coach-comfort",
        app_config.agents.comfort.prompts.instruction,
    )
    comfort_node = ComfortNode(
        llm=_make_eval_llm(app_config.agents.comfort.model),
        system_prompt=comfort_text,
        langfuse_prompt=comfort_prompt,
    )

    assessment_text, assessment_prompt = _get(
        "money-coach-assessment",
        app_config.agents.assessment.prompts.instruction,
    )
    assessment_node = AssessmentNode(
        llm=_make_eval_llm(app_config.agents.assessment.model),
        system_prompt=assessment_text,
        langfuse_prompt=assessment_prompt,
    )

    classifier_text, classifier_prompt = _get(
        "money-coach-classifier",
        app_config.agents.classifier.prompts.instruction,
    )
    classifier_node = ClassifierNode(
        llm=_make_eval_llm(app_config.agents.classifier.model),
        system_prompt=classifier_text,
        langfuse_prompt=classifier_prompt,
    )

    escalate_node = EscalateNode()

    main_text, main_prompt = _get(
        "money-coach-main",
        app_config.agents.main.prompts.instruction,
    )
    coach_prompt_template = ChatPromptTemplate(
        [("system", main_text), ("placeholder", "{messages}")],
        metadata={"langfuse_prompt": main_prompt} if main_prompt else {},
    )
    coach_node = CoachNode(
        coach_graph=create_react_agent(
            model=_make_eval_llm(app_config.agents.main.model),
            tools=_TOOLS,
            prompt=coach_prompt_template,
        )
    )

    # --- routing (identical to production graph) ---

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

    # --- compile ---

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
        "assessment", route_assessment, {"classifier": "classifier", END: END}
    )
    builder.add_conditional_edges(
        "classifier", route_case, {"escalate": "escalate", "coach": "coach"}
    )
    builder.add_edge("escalate", END)
    builder.add_edge("coach", END)

    return builder.compile()
