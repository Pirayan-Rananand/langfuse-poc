"""LLM judge: evaluates a candidate response against the gold reference."""

import json
import logging
from typing import NamedTuple

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from evaluation.dataset.schema import DatasetItemExpectedOutput, DatasetItemInput
from evaluation.judge.dimensions import DIMENSIONS
from evaluation.judge.prompt import build_judge_prompt

logger = logging.getLogger(__name__)


class DimensionScore(NamedTuple):
    name: str
    score: float    # raw 0-10
    weight: float
    reasoning: str


class EvaluationResult(NamedTuple):
    dimension_scores: list[DimensionScore]
    composite_score: float  # weighted average normalised to 0-1


def make_llm_judge(judge_model: str, api_key: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=judge_model,
        temperature=0.0,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        disable_streaming=True,
    )


def _neutral_result(reason: str = "judge failed") -> EvaluationResult:
    return EvaluationResult(
        dimension_scores=[
            DimensionScore(d.name, 5.0, d.weight, reason) for d in DIMENSIONS
        ],
        composite_score=0.5,
    )


def evaluate_response(
    llm: ChatOpenAI,
    item_input: DatasetItemInput,
    candidate_output: str,
    expected_output: DatasetItemExpectedOutput,
) -> EvaluationResult:
    """Run the LLM judge and return per-dimension scores + composite."""
    if not candidate_output:
        return _neutral_result("empty candidate output")

    prompt_text = build_judge_prompt(item_input, candidate_output, expected_output)

    try:
        response = llm.invoke([HumanMessage(content=prompt_text)])
        content = response.content.strip()

        # Strip markdown code fences if the model wraps its JSON
        if content.startswith("```"):
            lines = content.splitlines()
            inner = lines[1:] if lines[0].startswith("```") else lines
            content = "\n".join(inner[:-1] if inner[-1].strip() == "```" else inner)

        scores_json = json.loads(content)
    except Exception as exc:
        logger.error("Judge LLM failed: %s", exc)
        return _neutral_result(f"judge error: {exc}")

    dimension_scores: list[DimensionScore] = []
    for dim in DIMENSIONS:
        raw = scores_json.get(dim.name, {})
        score = float(raw.get("score", 5.0))
        score = max(0.0, min(10.0, score))  # clamp to [0, 10]
        reasoning = str(raw.get("reasoning", ""))
        dimension_scores.append(DimensionScore(dim.name, score, dim.weight, reasoning))

    composite = sum(ds.score * ds.weight / 10.0 for ds in dimension_scores)
    return EvaluationResult(dimension_scores=dimension_scores, composite_score=composite)
