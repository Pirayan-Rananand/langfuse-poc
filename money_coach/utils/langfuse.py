"""Prompt resolution — Langfuse as source-of-truth, agents.yaml as fallback.

LANGFUSE_TRACING_ENVIRONMENT → Langfuse label:
  dev               → "development"
  sit               → "sit"
  canary            → "canary"
  prod / production → "production"  (default)
"""

import logging
import os

from langfuse import get_client

logger = logging.getLogger(__name__)

_ENV_TO_LABEL: dict[str, str] = {
    "dev": "development",
    "sit": "sit",
    "canary": "canary",
    "prod": "production",
    "production": "production",
}


def _prompt_label() -> str:
    env = os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "prod").lower()
    return _ENV_TO_LABEL.get(env, "production")


def fetch_prompt(name: str, fallback: str) -> str:
    """Return prompt text from Langfuse, falling back to `fallback` on any error."""
    try:
        label = _prompt_label()
        prompt = get_client().get_prompt(name, label=label)
        logger.debug("Loaded prompt '%s' (label=%s) from Langfuse", name, label)
        return prompt.prompt
    except Exception as exc:
        logger.warning(
            "Could not fetch prompt '%s' from Langfuse (%s) — using fallback",
            name,
            exc,
        )
        return fallback, None


def fetch_prompt_by_label(
    client,
    name: str,
    label: str,
    fallback: str,
) -> tuple[str, object | None]:
    """Like fetch_prompt but with explicit client + label. Used by eval pipeline."""
    try:
        prompt = client.get_prompt(name, label=label)
        logger.debug("Loaded prompt '%s' (label=%s) from Langfuse", name, label)
        return prompt.prompt, prompt
    except Exception as exc:
        logger.warning(
            "Could not fetch '%s' (label=%s): %s — using fallback", name, label, exc
        )
        return fallback, None
