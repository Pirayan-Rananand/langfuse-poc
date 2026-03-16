"""Compare baseline vs candidate evaluation results and decide pass/fail."""

import logging
from dataclasses import dataclass

from evaluation.judge.evaluator import EvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class ItemComparison:
    item_id: str
    baseline_composite: float
    candidate_composite: float
    delta: float   # candidate - baseline


@dataclass
class ComparisonReport:
    baseline_mean: float
    candidate_mean: float
    threshold: float            # required multiplier (e.g. 1.03)
    required_score: float       # baseline_mean * threshold
    passed: bool
    item_comparisons: list[ItemComparison]
    n_items: int


def compare_runs(
    baseline_results: dict[str, EvaluationResult],
    candidate_results: dict[str, EvaluationResult],
    threshold: float = 1.03,
) -> ComparisonReport:
    """Compare candidate vs baseline.

    Passed when candidate_mean >= baseline_mean * threshold.
    Only items present in both result sets are compared.
    """
    item_ids = sorted(set(baseline_results) & set(candidate_results))

    if not item_ids:
        logger.warning("No overlapping items between baseline and candidate results")
        return ComparisonReport(
            baseline_mean=0.0,
            candidate_mean=0.0,
            threshold=threshold,
            required_score=0.0,
            passed=False,
            item_comparisons=[],
            n_items=0,
        )

    comparisons = [
        ItemComparison(
            item_id=item_id,
            baseline_composite=baseline_results[item_id].composite_score,
            candidate_composite=candidate_results[item_id].composite_score,
            delta=candidate_results[item_id].composite_score
            - baseline_results[item_id].composite_score,
        )
        for item_id in item_ids
    ]

    baseline_mean = sum(c.baseline_composite for c in comparisons) / len(comparisons)
    candidate_mean = sum(c.candidate_composite for c in comparisons) / len(comparisons)
    required_score = baseline_mean * threshold

    return ComparisonReport(
        baseline_mean=baseline_mean,
        candidate_mean=candidate_mean,
        threshold=threshold,
        required_score=required_score,
        passed=candidate_mean >= required_score,
        item_comparisons=comparisons,
        n_items=len(comparisons),
    )
