# Money Coach — task runner
# Usage: just <recipe>   (install: brew install just)

# Show available recipes
default:
    @just --list

# ─────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────

# Start LangGraph dev server (hot-reload, Studio UI at http://127.0.0.1:2024)
dev:
    uv run langgraph dev

# Run CLI smoke-test loop (interactive chat)
chat:
    uv run python -m money_coach.main

# ─────────────────────────────────────────────
# Dataset seeding
# ─────────────────────────────────────────────

# Preview what would be seeded — no writes (default: 5 items)
seed-dry max="5":
    uv run python -m evaluation.seed_dataset --dry-run --max-items {{ max }}

# Seed dataset, skip if already populated (default: 50 items)
seed max="50":
    uv run python -m evaluation.seed_dataset --max-items {{ max }} --skip-if-not-empty

# Force re-seed from nonprod traces (overwrites existing items)
seed-force max="50":
    uv run python -m evaluation.seed_dataset --force-reseed --max-items {{ max }}

# Seed from prod traces (use once prod has enough data)
seed-prod max="50":
    uv run python -m evaluation.seed_dataset --source prod --max-items {{ max }} --skip-if-not-empty

# ─────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────

# Compare a specific prompt version vs production baseline
# Usage: just eval money-coach-main 7
eval prompt version threshold="1.03":
    uv run python -m evaluation.run_experiment \
      --candidate-prompt-name {{ prompt }} \
      --candidate-version {{ version }} \
      --baseline-label production \
      --threshold {{ threshold }}

# Compare a label vs production baseline (no version pinning)
# Usage: just eval-label development
eval-label candidate="development" baseline="production":
    uv run python -m evaluation.run_experiment \
      --candidate-label {{ candidate }} \
      --baseline-label {{ baseline }}

# Full pipeline: seed (skip if populated) then evaluate a specific version
# Usage: just promote money-coach-main 7
promote prompt version threshold="1.03":
    @just seed
    @just eval {{ prompt }} {{ version }} {{ threshold }}

# ─────────────────────────────────────────────
# Development helpers
# ─────────────────────────────────────────────

# Install dependencies
install:
    uv sync

# Run linter
lint:
    uv run ruff check .

# Run type checker
typecheck:
    uv run pyright

# Run tests
test:
    uv run pytest
