# AGENTS.md

## Project: Money Coach

Thai-language financial coaching agent built with LangGraph + Langfuse.

- **Runtime**: Python 3.12+, managed by `uv`
- **LLM provider**: OpenRouter (Google Gemini 2.5 Flash)
- **Orchestration**: LangGraph (StateGraph with conditional routing)
- **Observability**: Langfuse (tracing, prompt management, evaluation datasets)
- **Task runner**: `just` (see `justfile` for all recipes)
- **Entry point**: `money_coach/graph/graph.py` exports `graph` for `langgraph dev`

---

## Quick Reference

```bash
just dev          # LangGraph Studio at http://127.0.0.1:2024
just chat         # CLI smoke-test loop
just eval <prompt> <version> [threshold]   # eval a prompt version vs production
just eval-label development production     # eval by label
just promote <prompt> <version>            # seed + eval in one step
just seed         # seed eval dataset from nonprod traces
just lint         # ruff check .
just typecheck    # pyright
just test         # pytest
```

---

## Engineering Principles

- **Dependency Injection first.** Pass dependencies via constructor/function args. Never instantiate services inside business logic.
- **Testable components.** Every node, tool, and service must be testable in isolation.
- **Business logic independent from infrastructure.** `core/` must not import from `infrastructure/`.
- **Explicit inputs and outputs.** No hidden side effects. Each pipeline stage accepts explicit inputs and produces explicit outputs.
- **Simple over clever.** Favor readable code over abstractions. Three similar lines > premature helper function.
- **No global state.** Pass artifacts explicitly between stages.

---

## Architecture

### Graph Flow

```
START → emotional_gate
         ├─ distressed       → comfort    → END
         └─ ready
              ├─ not_completed → assessment
              │                   ├─ still gathering → END
              │                   └─ completed       → classifier
              │                                         ├─ RED    → escalate → END
              │                                         └─ other  → coach    → END
              └─ completed
                   ├─ RED        → escalate → END
                   └─ other      → coach    → END
```

### State Schema (`money_coach/state/state.py`)

| Field | Type | Values |
|-------|------|--------|
| `messages` | `list[BaseMessage]` | Conversation history (add_messages reducer) |
| `emotional_state` | `str` | `"unknown"` / `"ready"` / `"distressed"` |
| `assessment_phase` | `str` | `"not_started"` / `"in_progress"` / `"completed"` |
| `assessment_data` | `dict` | Accumulated financial answers |
| `debt_case` | `str` | `"unknown"` / `"healthy"` / `"yellow"` / `"orange"` / `"red"` |

### Node Pattern

All nodes follow this constructor pattern (see `emotional_gate.py` as reference):

```python
class SomeNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str, langfuse_prompt=None):
        # Build chain: ChatPromptTemplate | structured_llm_or_chain
        # Attach langfuse_prompt as metadata for tracing
        ...

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        # Invoke chain, return state updates
        ...
```

When adding a new node:
1. Create `money_coach/graph/nodes/<name>.py` following the pattern above
2. Export from `money_coach/graph/nodes/__init__.py`
3. Add prompt to Langfuse with name `money-coach-<name>`
4. Add fallback prompt to `money_coach/configs/agents.yaml`
5. Wire into `build_graph()` in `graph.py` with `fetch_prompt()` + routing

### Prompt Management

- **Source of truth**: Langfuse prompt store
- **Fallback**: `money_coach/configs/agents.yaml` (used when Langfuse is unreachable)
- **Label mapping** (`LANGFUSE_TRACING_ENVIRONMENT` → Langfuse label):
  - `dev` → `"development"`, `sit` → `"sit"`, `canary` → `"canary"`, `prod` → `"production"`
- **Prompt names**: `money-coach-emotional-gate`, `money-coach-comfort`, `money-coach-assessment`, `money-coach-classifier`, `money-coach-main`
- **`create_react_agent` uses `prompt=` kwarg**, NOT `state_modifier=` (deprecated)

### Prompt Promotion Pipeline (CI/CD)

```
Langfuse webhook (nonprod "production" label)
  → GitHub Action: cd-sync-prompt-from-langfuse.yaml
    → Reusable workflow: prompt-promotion-pipeline.yaml
      Job 1: Sync prompt to prod Langfuse (no label)
      Job 2: Seed dataset + run eval (candidate vs production baseline)
      Job 3: If eval passes → tag "canary" in prod
```

### Dual Langfuse Client Pattern

- **Nonprod** (`LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY`): dev traces, datasets, eval results
- **Prod** (`LANGFUSE_PROD_SECRET_KEY` / `LANGFUSE_PROD_PUBLIC_KEY`): production prompt versions
- Factory functions in `evaluation/langfuse_clients.py`

---

## Evaluation Pipeline

### Running Evals

```bash
# Compare specific version against production baseline
just eval money-coach-main 7 1.03

# Compare labels
just eval-label development production

# Full pipeline: seed + eval
just promote money-coach-main 7
```

### Five Evaluation Dimensions

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| `financial_accuracy` | 0.30 | Numbers, DTI, strategy correctness |
| `advice_actionability` | 0.25 | Concrete steps, specific amounts/timelines |
| `completeness` | 0.20 | All concerns addressed, no skipped issues |
| `empathy` | 0.15 | Warm tone, non-judgmental, supportive |
| `language_quality` | 0.10 | Natural Thai, appropriate register |

- Score range: 0-10 per dimension, weighted composite 0.0-1.0
- **Pass threshold**: `candidate_mean >= baseline_mean * threshold` (default 1.03 = 3% improvement)
- When interpreting eval results, identify the weakest dimension and suggest targeted prompt edits

### Dataset

- Source: seeded from Langfuse traces via `evaluation/seed_dataset.py`
- Schema: `DatasetItemInput` (messages, assessment_data, debt_case, emotional_state, assessment_phase) + `DatasetItemExpectedOutput` (final_message, terminal_node)
- Items route to the `coach` node (assessment_phase="completed", emotional_state="ready")

---

## Available Tools & Integrations

### CodeGraph (MCP)

This project has `.codegraph/` initialized. Use these tools for **fast code exploration** instead of grep/glob:

| Tool | Use For |
|------|---------|
| `codegraph_search` | Find symbols by name (functions, classes, types) |
| `codegraph_context` | Get relevant code context for a task |
| `codegraph_callers` | Find what calls a function |
| `codegraph_callees` | Find what a function calls |
| `codegraph_impact` | See what's affected by changing a symbol |
| `codegraph_node` | Get details + source code for a symbol |
| `codegraph_files` | Get project file structure from the index |
| `codegraph_status` | Check index health |

**Prefer codegraph over grep** for symbol lookups. Use `codegraph_impact` before refactoring to understand blast radius.

When spawning subagents (Explore, general-purpose), tell them to use codegraph tools.

### Excalidraw (MCP)

Use for creating architecture diagrams, flow charts, and visual documentation.

| Tool | Use For |
|------|---------|
| `Excalidraw:create_view` | Create a new diagram |
| `Excalidraw:export_to_excalidraw` | Export to .excalidraw format |
| `Excalidraw:read_checkpoint` | Read saved diagram state |
| `Excalidraw:save_checkpoint` | Save diagram state |

Use when the user asks for visual explanations of the graph flow, architecture, or evaluation pipeline.

### Langfuse Skill

Invoke with `/langfuse`. Use for:
- Querying Langfuse data (traces, prompts, datasets, scores, sessions)
- Looking up Langfuse documentation and SDK usage
- Understanding Langfuse features and integration patterns

### Pyright LSP (Plugin)

Type checking is available via the Pyright plugin. Use `getDiagnostics` to check for type errors after edits.

---

## Key Files

| File | Purpose |
|------|---------|
| `money_coach/graph/graph.py` | Main graph builder, exports `graph` singleton |
| `money_coach/graph/nodes/*.py` | Individual node implementations |
| `money_coach/state/state.py` | Shared TypedDict state schema |
| `money_coach/utils/langfuse.py` | `fetch_prompt()` — Langfuse with fallback |
| `money_coach/configs/agents.yaml` | Fallback prompts (Thai) + agent metadata |
| `money_coach/configs/model.py` | Pydantic config models |
| `money_coach/agent_tools/financial.py` | 4 pure-Python financial tools |
| `money_coach/dependencies.py` | Langfuse client singleton + handler factory |
| `evaluation/run_experiment.py` | Eval CLI — orchestrates seed, run, judge, compare |
| `evaluation/judge/dimensions.py` | 5 eval dimensions with weights |
| `evaluation/judge/evaluator.py` | LLM judge implementation |
| `evaluation/runner/graph_factory.py` | Builds eval-specific graphs with prompt overrides |
| `evaluation/langfuse_clients.py` | Nonprod/prod client factories |
| `.github/workflows/prompt-promotion-pipeline.yaml` | CI/CD: sync → eval → canary |
| `langgraph.json` | LangGraph server config |
| `justfile` | Task runner recipes |

---

## Anti-Patterns

- **No hardcoded LLM calls in business logic.** Always go through the node pattern.
- **No global state.** Pass state explicitly via the LangGraph State dict.
- **No monolithic scripts.** Each node, tool, and eval component must be independently testable.
- **No tightly coupled pipelines.** Each eval stage (seed, run, judge, compare) runs independently.
- **No unnecessary abstractions.** Don't create helpers for one-time operations.
- **No env var access in business logic.** Config flows through `AppConfig` or function args.

---

## Environment Variables

See `.env.example` for the full list. Key groups:

- **LLM**: `OPENROUTER_API_KEY`
- **Langfuse nonprod**: `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`
- **Langfuse prod**: `LANGFUSE_PROD_SECRET_KEY`, `LANGFUSE_PROD_PUBLIC_KEY` (CI/CD only)
- **Langfuse config**: `LANGFUSE_BASE_URL`, `LANGFUSE_TRACING_ENVIRONMENT`, `LANGFUSE_TIMEOUT`
- **Eval**: `EVAL_DATASET_NAME`, `EVAL_PROMOTION_THRESHOLD`, `EVAL_JUDGE_MODEL`
- **GitHub**: `GITHUB_TOKEN`, `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`

All observability is no-op when env vars are absent. Safe to run without any keys (falls back to agents.yaml for prompts).
