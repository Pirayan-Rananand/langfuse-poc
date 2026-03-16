# Evaluation Pipeline

Automated prompt evaluation for the Money Coach LLM. Prevents regressions from
reaching production by running a candidate prompt against a scored baseline before
the prompt is served to real users.

---

## Promotion Flow

```
[Developer]
  1. Create/iterate on prompt in nonprod Langfuse  →  label: dev
  2. Validate locally                              →  move label to sit
  3. Validate in SIT                               →  move label to production (in nonprod)

[GitHub Actions — triggered by Langfuse webhook on nonprod "production" label]
  4. sync-to-prod   POST prompt to prod Langfuse with labels: []
                    (unlabeled version serves no traffic — failure is harmless)
                    → outputs: prompt_name, prompt_version

  5. auto-eval      Seed dataset from nonprod traces (idempotent, skips if populated)
                    Run eval: candidate (prod/new-version) vs baseline (prod/production)
                    → outputs: eval_passed = true | false

  6. tag-canary     Only if eval_passed=true: PATCH prod → assign "canary" label

[Developer]
  7. Monitor canary metrics in prod
  8. Manually assign "production" label in prod Langfuse when satisfied
```

---

## Module Structure

```
evaluation/
├── config.py                   # EvalConfig — reads env vars (threshold, model, dataset name)
├── langfuse_clients.py         # make_nonprod_client() / make_prod_client() — injected, no globals
├── dataset/
│   ├── schema.py               # DatasetItemInput / DatasetItemExpectedOutput TypedDicts
│   └── seeder.py               # TraceSeeder — seeds dataset from completed nonprod traces
├── runner/
│   ├── graph_factory.py        # build_eval_graph() — wires graph with overridden prompt versions
│   └── task.py                 # make_task(graph) → callable for dataset items
├── judge/
│   ├── dimensions.py           # 5 weighted dimensions with Thai rubrics
│   ├── prompt.py               # build_judge_prompt() — formats judge input
│   └── evaluator.py            # evaluate_response() → EvaluationResult (scores + composite)
├── comparison/
│   └── comparator.py           # compare_runs() → ComparisonReport (pass/fail)
├── seed_dataset.py             # CLI entrypoint
└── run_experiment.py           # CLI entrypoint
```

---

## Dataset

### Source

Dataset items are seeded from **nonprod traces** (dev/sit conversations). This avoids
the cold-start problem where prod has no data.

Each item captures a completed coach conversation:

```python
# Input — fed to the eval graph (assessment_phase="completed" routes directly to coach)
{
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},  # prior turns
    {"role": "user", "content": "..."}        # last user message
  ],
  "assessment_data": { "monthly_income": 50000, "debts": [...], ... },
  "debt_case": "yellow",          # "healthy" | "yellow" | "orange"
  "emotional_state": "ready",
  "assessment_phase": "completed"
}

# Expected output — gold reference
{
  "final_message": "...",   # original coach response from the trace
  "terminal_node": "coach"
}
```

`TraceSeeder` filters for traces where `assessment_phase == "completed"` and
`debt_case` is a coach case (not `red`/escalate).

### Seeding

```bash
# Preview what would be seeded (no writes)
uv run python -m evaluation.seed_dataset --dry-run --max-items 5

# Seed up to 50 items, skip if dataset already has data
uv run python -m evaluation.seed_dataset --max-items 50 --skip-if-not-empty

# Force re-seed (refresh with newer traces)
uv run python -m evaluation.seed_dataset --force-reseed

# Use prod traces once prod has enough data
uv run python -m evaluation.seed_dataset --source prod
```

The dataset is stored in the **nonprod** Langfuse project under the name configured
by `EVAL_DATASET_NAME` (default: `money-coach-eval-v1`).

---

## Evaluation

Two graphs are built for each experiment run:

| Graph | Prompt source |
|-------|--------------|
| **Baseline** | All prompts fetched from prod by `--baseline-label` (default: `production`) |
| **Candidate** | Target prompt fetched by exact version number; all others stay on baseline label |

Both graphs run on every dataset item. The final AI message from the coach node is
collected as the output.

### Judge

An LLM judge (via OpenRouter) scores each output on 5 dimensions:

| Dimension | Weight | Focus |
|-----------|--------|-------|
| `financial_accuracy` | 30% | Correct numbers, right strategy, DTI correct |
| `advice_actionability` | 25% | Specific steps, not vague |
| `completeness` | 20% | Addresses all user concerns |
| `empathy` | 15% | Warm, non-judgmental tone |
| `language_quality` | 10% | Natural Thai, correct formality |

Each dimension is scored 0–10. The **composite score** is the weighted average
normalised to 0–1:

```
composite = Σ (dimension_score / 10 × weight)
```

### Pass Condition

```
candidate_mean >= baseline_mean × threshold
```

Default threshold: `1.03` (candidate must score at least 3% above baseline).

Scores and per-dimension reasoning are logged to the nonprod Langfuse
**Experiments** tab for side-by-side comparison.

### Running Locally

```bash
# Compare a specific prod version vs production baseline
uv run python -m evaluation.run_experiment \
  --candidate-prompt-name money-coach-main \
  --candidate-version 7 \
  --baseline-label production \
  --threshold 1.03
# exits 0 = passed, 1 = failed

# Compare two labels (no version pinning)
uv run python -m evaluation.run_experiment \
  --candidate-label development \
  --baseline-label production
```

---

## GitHub Actions Workflows

### `prompt-promotion-pipeline.yaml` — reusable template

Contains the full 3-job pipeline (`sync-to-prod` → `auto-eval` → `tag-canary`).
Called via `workflow_call` — not triggered directly.

**Inputs:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt_json` | string | required | Full Langfuse prompt object as JSON |
| `threshold` | string | `"1.03"` | Composite score multiplier to pass eval |
| `seed_max_items` | number | `50` | Max traces to seed into dataset |

**Outputs:** `prompt_name`, `prompt_version`, `eval_passed`

**Secrets required:** `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_PROD_PUBLIC_KEY`, `LANGFUSE_PROD_SECRET_KEY`, `OPENROUTER_API_KEY`

To reuse this pipeline for a different prompt source, create a new trigger file:

```yaml
jobs:
  promote:
    uses: ./.github/workflows/prompt-promotion-pipeline.yaml
    with:
      prompt_json: ${{ toJson(your.prompt.payload) }}
      threshold: "1.05"
    secrets: inherit
```

### `cd-sync-prompt-from-langfuse.yaml` — Langfuse webhook trigger

Listens for `repository_dispatch` events from Langfuse. Calls the reusable pipeline
only when the nonprod prompt has the `production` label. Also accepts
`workflow_dispatch` for manual testing.

```
Langfuse nonprod webhook
        │  (label = production)
        ▼
  cd-sync-prompt-from-langfuse.yaml
        │  uses:
        ▼
  prompt-promotion-pipeline.yaml
    ├── sync-to-prod   (always runs)
    ├── auto-eval      (always runs, needs sync-to-prod)
    └── tag-canary     (only if eval_passed=true)
```

---

## Configuration

All values can be set in `.env` or passed as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `EVAL_DATASET_NAME` | `money-coach-eval-v1` | Langfuse dataset name |
| `EVAL_PROMOTION_THRESHOLD` | `1.03` | Pass threshold for `run_experiment` |
| `EVAL_JUDGE_MODEL` | `google/gemini-2.5-flash` | OpenRouter model used as judge |
| `LANGFUSE_SECRET_KEY` | — | Nonprod Langfuse secret (dataset + traces) |
| `LANGFUSE_PUBLIC_KEY` | — | Nonprod Langfuse public key |
| `LANGFUSE_PROD_SECRET_KEY` | — | Prod Langfuse secret (prompt versions) |
| `LANGFUSE_PROD_PUBLIC_KEY` | — | Prod Langfuse public key |
| `OPENROUTER_API_KEY` | — | API key for judge LLM and eval graphs |

---

## GitHub Actions Secrets Required

Add these in **Settings → Secrets and variables → Actions**:

- `LANGFUSE_SECRET_KEY` — nonprod project
- `LANGFUSE_PUBLIC_KEY` — nonprod project
- `LANGFUSE_PROD_SECRET_KEY` — prod project
- `LANGFUSE_PROD_PUBLIC_KEY` — prod project
- `OPENROUTER_API_KEY`
