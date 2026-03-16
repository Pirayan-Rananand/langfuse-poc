"""CLI: Run a prompt evaluation experiment comparing candidate vs baseline.

Usage:
    # Compare a specific version against production (used by GitHub Action)
    uv run python -m evaluation.run_experiment \\
      --candidate-prompt-name money-coach-main \\
      --candidate-version 7 \\
      --baseline-label production \\
      --threshold 1.03

    # Compare two labels (manual / local use)
    uv run python -m evaluation.run_experiment \\
      --candidate-label development \\
      --baseline-label production

Exit codes:
    0 — eval passed  (candidate_mean >= baseline_mean * threshold)
    1 — eval failed or error
"""

import argparse
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _log_run_to_langfuse(
    nonprod_client,
    item,
    run_name: str,
    output: str,
    eval_result,
) -> None:
    """Create a trace in nonprod Langfuse linked to the dataset item run."""
    try:
        trace = nonprod_client.trace(
            name="eval-run",
            input=item.input,
            output={"response": output},
            metadata={"run_name": run_name, "dataset_item_id": item.id},
        )
        # Link trace to dataset item run (Langfuse Experiments UI)
        try:
            item.link(trace, run_name=run_name)
        except AttributeError:
            pass  # older SDK version without item.link

        for ds in eval_result.dimension_scores:
            nonprod_client.score(
                trace_id=trace.id,
                name=ds.name,
                value=ds.score,
                comment=ds.reasoning,
            )
        nonprod_client.score(
            trace_id=trace.id,
            name="composite",
            value=round(eval_result.composite_score * 10, 3),
            comment=f"Weighted composite ({run_name})",
        )
        nonprod_client.flush()
    except Exception as exc:
        logger.warning("Failed to log scores to Langfuse: %s", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run prompt evaluation experiment")

    # Candidate: specific version OR label (mutually exclusive)
    candidate_group = parser.add_mutually_exclusive_group()
    candidate_group.add_argument(
        "--candidate-version",
        type=int,
        help="Candidate prompt version number in prod Langfuse",
    )
    candidate_group.add_argument(
        "--candidate-label",
        help="Candidate prompt label (e.g. development, sit)",
    )
    parser.add_argument(
        "--candidate-prompt-name",
        default="money-coach-main",
        help="Name of the prompt being tested (default: money-coach-main)",
    )
    parser.add_argument("--baseline-label", default="production")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Composite score multiplier required to pass (default: EVAL_PROMOTION_THRESHOLD or 1.03)",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Override dataset name (default: EVAL_DATASET_NAME env or money-coach-eval-v1)",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Label for this experiment run in Langfuse Experiments UI",
    )
    args = parser.parse_args(argv)

    from evaluation.comparison.comparator import compare_runs
    from evaluation.config import EvalConfig
    from evaluation.judge.evaluator import evaluate_response, make_llm_judge
    from evaluation.langfuse_clients import make_nonprod_client, make_prod_client
    from evaluation.runner.graph_factory import build_eval_graph
    from evaluation.runner.task import make_task
    from money_coach.configs import agent_config

    config = EvalConfig()
    threshold = args.threshold if args.threshold is not None else config.promotion_threshold
    dataset_name = args.dataset_name or config.dataset_name

    nonprod_client = make_nonprod_client()
    prod_client = make_prod_client()

    # --- determine candidate configuration ---
    prompt_overrides: dict[str, int] = {}
    run_suffix = uuid.uuid4().hex[:6]

    if args.candidate_version is not None:
        prompt_overrides[args.candidate_prompt_name] = args.candidate_version
        candidate_fallback_label = args.baseline_label  # other prompts stay on baseline
        run_name = args.run_name or f"candidate-v{args.candidate_version}-{run_suffix}"
    elif args.candidate_label:
        candidate_fallback_label = args.candidate_label
        run_name = args.run_name or f"candidate-{args.candidate_label}-{run_suffix}"
    else:
        candidate_fallback_label = "development"
        run_name = args.run_name or f"candidate-development-{run_suffix}"

    baseline_run_name = f"baseline-{args.baseline_label}-{run_suffix}"

    # --- build graphs ---
    logger.info(
        "Building candidate graph  overrides=%s  fallback_label=%s",
        prompt_overrides or "none",
        candidate_fallback_label,
    )
    candidate_graph = build_eval_graph(
        prod_client=prod_client,
        app_config=agent_config,
        prompt_overrides=prompt_overrides or None,
        fallback_label=candidate_fallback_label,
    )
    candidate_task = make_task(candidate_graph)

    logger.info("Building baseline graph  label=%s", args.baseline_label)
    baseline_graph = build_eval_graph(
        prod_client=prod_client,
        app_config=agent_config,
        prompt_overrides=None,
        fallback_label=args.baseline_label,
    )
    baseline_task = make_task(baseline_graph)

    # --- fetch dataset ---
    logger.info("Fetching dataset '%s' from nonprod", dataset_name)
    try:
        dataset = nonprod_client.get_dataset(dataset_name)
        items = dataset.items
    except Exception as exc:
        logger.error("Failed to fetch dataset '%s': %s", dataset_name, exc)
        return 1

    if not items:
        logger.error(
            "Dataset '%s' has no items — run `uv run python -m evaluation.seed_dataset` first",
            dataset_name,
        )
        return 1

    logger.info("Evaluating %d dataset items", len(items))

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    judge_llm = make_llm_judge(config.judge_model, openrouter_key)

    baseline_results = {}
    candidate_results = {}

    for i, item in enumerate(items, 1):
        logger.info("Item %d/%d  id=%s", i, len(items), item.id)

        # Run baseline
        try:
            baseline_output = baseline_task(item.input) or ""
        except Exception as exc:
            logger.error("Baseline failed for item %s: %s", item.id, exc)
            baseline_output = ""

        # Run candidate
        try:
            candidate_output = candidate_task(item.input) or ""
        except Exception as exc:
            logger.error("Candidate failed for item %s: %s", item.id, exc)
            candidate_output = ""

        expected = item.expected_output or {"final_message": "", "terminal_node": "coach"}

        # Judge
        baseline_eval = evaluate_response(judge_llm, item.input, baseline_output, expected)
        candidate_eval = evaluate_response(judge_llm, item.input, candidate_output, expected)

        baseline_results[item.id] = baseline_eval
        candidate_results[item.id] = candidate_eval

        # Log to Langfuse
        _log_run_to_langfuse(nonprod_client, item, baseline_run_name, baseline_output, baseline_eval)
        _log_run_to_langfuse(nonprod_client, item, run_name, candidate_output, candidate_eval)

        logger.info(
            "  baseline=%.3f  candidate=%.3f  delta=%+.3f",
            baseline_eval.composite_score,
            candidate_eval.composite_score,
            candidate_eval.composite_score - baseline_eval.composite_score,
        )

    # --- compare ---
    report = compare_runs(baseline_results, candidate_results, threshold=threshold)

    logger.info("=" * 60)
    logger.info("EVALUATION REPORT")
    logger.info("  Items evaluated : %d", report.n_items)
    logger.info("  Baseline mean   : %.4f", report.baseline_mean)
    logger.info("  Candidate mean  : %.4f", report.candidate_mean)
    logger.info(
        "  Required score  : %.4f  (baseline × %.2f)",
        report.required_score,
        threshold,
    )
    logger.info("  Result          : %s", "PASSED" if report.passed else "FAILED")
    logger.info("=" * 60)

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
