"""CLI: Seed the evaluation dataset from Langfuse traces.

Usage:
    # Dry run — preview what would be seeded (no writes)
    uv run python -m evaluation.seed_dataset --dry-run --max-items 5

    # Seed up to 50 items, skip if dataset already has data
    uv run python -m evaluation.seed_dataset --max-items 50 --skip-if-not-empty

    # Force re-seed even if dataset has items
    uv run python -m evaluation.seed_dataset --force-reseed

    # Use prod traces as source (once prod has enough data)
    uv run python -m evaluation.seed_dataset --source prod

Exit codes: 0 = success, 1 = error.
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed evaluation dataset from Langfuse traces")
    parser.add_argument(
        "--source",
        choices=["nonprod", "prod"],
        default="nonprod",
        help="Which Langfuse project to pull traces from (default: nonprod)",
    )
    parser.add_argument("--max-items", type=int, default=50)
    parser.add_argument(
        "--skip-if-not-empty",
        action="store_true",
        help="Skip seeding if the dataset already contains items",
    )
    parser.add_argument(
        "--force-reseed",
        action="store_true",
        help="Seed even if the dataset already has items (overrides --skip-if-not-empty)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be seeded without writing anything",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Override dataset name (default: EVAL_DATASET_NAME env or money-coach-eval-v1)",
    )
    args = parser.parse_args(argv)

    from evaluation.config import EvalConfig
    from evaluation.dataset.seeder import TraceSeeder
    from evaluation.langfuse_clients import make_nonprod_client, make_prod_client

    config = EvalConfig()
    dataset_name = args.dataset_name or config.dataset_name

    client = make_nonprod_client() if args.source == "nonprod" else make_prod_client()

    seeder = TraceSeeder(
        nonprod_client=client,
        dataset_name=dataset_name,
        max_items=args.max_items,
    )

    skip = args.skip_if_not_empty and not args.force_reseed
    stats = seeder.seed(skip_if_not_empty=skip, dry_run=args.dry_run)

    mode = "[DRY RUN] " if args.dry_run else ""
    logger.info(
        "%sSeeding complete — fetched=%d  eligible=%d  seeded=%d",
        mode,
        stats.traces_fetched,
        stats.traces_eligible,
        stats.items_seeded,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
