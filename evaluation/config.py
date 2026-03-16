"""Evaluation pipeline configuration, read from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass
class EvalConfig:
    dataset_name: str = field(
        default_factory=lambda: os.getenv("EVAL_DATASET_NAME", "money-coach-eval-v1")
    )
    promotion_threshold: float = field(
        default_factory=lambda: float(os.getenv("EVAL_PROMOTION_THRESHOLD", "1.03"))
    )
    judge_model: str = field(
        default_factory=lambda: os.getenv("EVAL_JUDGE_MODEL", "google/gemini-2.5-flash")
    )
    max_dataset_items: int = 50
