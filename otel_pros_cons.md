# LangFuse vs Arize Phoenix — LLMOps Pipeline Comparison

> Context: Evaluated against the **LLM Prompt Versioning & Evaluation Workflow** planned pipeline (PDF: "Details: LLM Prompt Versioning & evaluation workflow").
> The pipeline requires: dual-environment prompt management, webhook-triggered CI/CD, auto-eval with LLM-as-judge, session tracking, and OTEL-compatible tracing.

---

## 1. Prompt Versioning

### LangFuse

**How it works:**
- Every save auto-increments a numeric `version`. Labels (`dev`, `sit`, `production`, `canary`, `latest`, etc.) are semantic pointers that move independently of versions.
- One version can hold multiple labels; the `latest` label is auto-maintained by LangFuse.
- SDK fetch: `get_prompt("name", label="production")` or `get_prompt("name", version=7)` for pinning.
- Rollback = reassign the `production` label to a prior version in UI — no code deploy needed.
- Built-in diff view between versions in the UI.
- Protected labels (Pro/Enterprise tier): prevents `member`/`viewer` roles from overwriting `production` label.

**Deployment label mapping (from planned pipeline):**

| Environment | LangFuse Project | Label |
|---|---|---|
| dev | nonprod | `dev` |
| SIT | nonprod | `sit` |
| canary | prod | `canary` |
| production | prod | `production` |
| synced (unlabeled) | prod | `<blank/latest>` |

**Limitations:**
- No native A/B traffic splitting by label (serving is all-or-nothing per label).
- No per-label access control below the Pro tier.
- Diff is visual-only — no API to programmatically retrieve a structured diff.

---

### Arize Phoenix

**How it works:**
- Phoenix has a **Prompt Management** feature (relatively new, v0.x), but it is primarily a playground/versioning store — not a deployment routing system.
- No label/environment concept: versions are stored but served only through the Phoenix UI or explicit SDK version pinning in code.
- No `get_prompt(label="production")` equivalent — runtime prompt resolution must be hand-coded.
- No built-in fallback/guaranteed-availability mechanism.

**Limitations:**
- **No environment-based label routing** for runtime prompt serving.
- **No promotion workflow** — cannot move a version to "production" state that services auto-pick up.
- **No conflict guard** for parallel Dev/DS promotion tracks.
- Prompt management is UI-centric with no CI/CD hooks.

**Verdict:** LangFuse wins decisively for the planned dual-track (Dev + DS) prompt versioning pipeline.

---

## 2. Webhooks & CI/CD Integration

### LangFuse

**Events fired:**
- `created` — new version saved.
- `updated` — labels or tags changed. **Two events fire**: one for the version that *gains* the label, one for the version that *loses* it.
- `deleted` — version removed.

**Payload structure:**
```json
{
  "id": "uuid",
  "timestamp": "2024-07-10T10:30:00Z",
  "type": "prompt-version",
  "apiVersion": "v1",
  "action": "created" | "updated" | "deleted",
  "prompt": {
    "name": "money-coach-main",
    "version": 7,
    "labels": ["production", "latest"],
    "prompt": "...",
    "type": "text",
    "config": {},
    "commitMessage": "...",
    "tags": [],
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

**GitHub Integration:**
- Built-in **Repository Dispatch** automation in the UI (`Prompts → Automations → Create Automation → GitHub Repository Dispatch`).
- Sends `client_payload` directly into `github.event.client_payload.prompt.*`.
- HMAC SHA-256 signature on `x-langfuse-signature` header for verification.
- Retries with exponential backoff on non-2xx responses.

**Known Limitations (confirmed by user):**

| Issue | Detail | Workaround |
|---|---|---|
| **Can't filter by label in webhook config** | The webhook fires on ANY `updated` event regardless of which label changed. You cannot set "only fire when label = production is assigned." | Add a middleware (Cloud Function / Cloud Run) that parses `prompt.labels` from payload and only forwards to GitHub dispatch if `"production" in labels`. |
| **Double-fire on label move** | When `production` moves from v6 → v7, two `updated` events fire: one for v7 (gains `production`) and one for v6 (loses `production`). Both arrive at your GitHub Action. | In the Cloud Function middleware: filter by `action == "updated" AND "production" in prompt.labels`. This drops the "loses label" event. |
| **No "label added" vs "label removed" distinction** | The event `action` is just `"updated"` for both cases — you must infer intent from the label array in the payload. | Same Cloud Function approach. |

**Middleware architecture for the planned pipeline:**
```
LangFuse webhook (updated)
  → Cloud Function
      if "production" in payload.prompt.labels
        and payload.action == "updated":
          POST → GitHub repository_dispatch
            { event_type: "langfuse-prompt-update",
              client_payload: { prompt_name, version, labels } }
```

---

### Arize Phoenix

- **No webhook system.** Phoenix has no native webhook or event emission for any state change.
- **No GitHub Actions integration.** No built-in way to trigger CI/CD from a prompt label change.
- Experiments can be triggered programmatically via Python SDK, but must be externally orchestrated (cron job, manual run, custom CI step).
- Any CI/CD integration requires fully custom scripting with Phoenix REST API.

**Verdict:** LangFuse is the only viable option for the planned automated prompt promotion pipeline. Phoenix requires full custom build for any CI/CD integration.

---

## 3. Auto-Eval & Datasets

### LangFuse

**Dataset creation methods:**
1. **Manual UI** — type input/expected output directly.
2. **CSV import** — bulk upload.
3. **Add from single trace** — click "Add to Dataset" from the trace detail view. One trace at a time.
4. **Batch add from Observations table** — select multiple observations → `Actions → Add to dataset`. Maps observation fields to dataset item fields.
5. **SDK** — `langfuse.create_dataset_item(dataset_name, input, expected_output)`.

**Known Limitation (confirmed by user):**
> _"Creating items from production data is supported on single trace level."_

The **UI trace → dataset** flow is one trace at a time. Batch seeding from traces requires custom SDK scripting (as implemented in `evaluation/dataset/seeder.py` in this project). There is no "select 50 traces and bulk-add as dataset items with full trace context (messages, metadata, debt_case)" in the UI.

**Scoring API:**
- Scores can be attached to: **traces**, **observations (spans)**, **dataset run items**.
- Fields: `trace_id | observation_id`, `name`, `value` (numeric), `comment`, `data_type` (NUMERIC/BOOLEAN/CATEGORICAL).
- `item.link(trace, run_name="candidate-v7")` links a trace to a dataset item run.
- **Experiments UI**: side-by-side comparison of baseline vs. candidate run scores per dataset item.

**LLM-as-Judge (server-side):**
- LangFuse has a built-in "LLM-as-a-Judge" evaluation feature (via `Scores → LLM-as-a-Judge`).
- Configurable templates, model selection (OpenAI, Anthropic, etc.), score dimensions.
- Can run server-side on existing traces without any SDK code — purely UI/API driven.
- **Limitation**: built-in judge runs on existing traces only; custom multi-dimensional weighted scoring (like the 5-dimension judge in this project) requires custom SDK code.

---

### Arize Phoenix

**Dataset creation methods:**
1. **Python SDK** — `px.Client().upload_dataset(dataframe)` or from a list of dicts.
2. **CSV upload** in UI.
3. **From traces in UI** — similar single-trace-or-span add.
4. No batch trace-to-dataset seeding built in (requires custom code similar to LangFuse).

**Experiments (Phoenix Evals):**
```python
import phoenix as px
from phoenix.evals import run_evals, llm_classify

# Run experiment on dataset
results = px.Client().run_experiment(
    dataset=dataset,
    task=my_task_fn,
    evaluators=[my_evaluator]
)
```

- `run_experiment()` is the core API: takes a dataset, a task function, and evaluators.
- Built-in evaluators: `llm_classify`, `llm_generate`, `hallucination`, `qa_correctness`, `relevance`, etc.
- Evaluator results are annotations (`label`, `score`, `explanation`) on spans/traces.
- Results visible in Phoenix UI under "Experiments" tab.
- **Strength**: evaluators are Python-first with a clean functional API. Easy to compose.

**Annotations (scoring) API:**
```python
client.spans.add_span_annotation(span_id, name, score, label, explanation, annotator_kind="LLM")
client.traces.add_trace_annotation(trace_id, name, score, label)
client.sessions.add_session_annotation(session_id, name, score)
```
- Granularity: span-level, trace-level, document-level (for RAG), session-level.
- Richer granularity than LangFuse (document-level, session-level annotations are native).

**Verdict:** Both support eval pipelines. LangFuse has the better UI integration with its Experiments tab and prompt-linked experiments. Phoenix has a cleaner programmatic eval API and richer annotation granularity. For the planned pipeline (custom LLM judge, baseline vs. candidate comparison), both require custom code — LangFuse scores marginally higher due to dataset-to-experiment UI linkage.

---

## 4. Trace UI & Sessions

### LangFuse

**Trace UI:**
- Hierarchical span tree: root trace → observations (generations/spans/events).
- Shows: model, input tokens, output tokens, cost, latency, tags, scores, metadata, user ID.
- Session Replay: linear timeline of all traces within a `sessionId` — reconstructs the full conversation chronologically.
- Filters: model, latency range, user, session, score threshold, tags, environment label.
- Annotation queues: assign traces to reviewers for human labeling.

**Sessions:**
- Group traces via `sessionId` string (≤200 chars).
- Propagated via `propagate_attributes(session_id="...")` or CallbackHandler.
- LangChain `thread_id` auto-maps to session in some integrations.
- Session replay: ordered message-by-message view — useful for debugging multi-turn conversations.
- **Limitation**: no per-session aggregate analytics (e.g., "average session length", "session completion rate") out-of-the-box — requires custom dashboard via Metrics API.

---

### Arize Phoenix

**Trace UI:**
- OTEL-native span tree based on OpenInference semantic conventions.
- Shows: span kind (LLM/RETRIEVER/TOOL/CHAIN), model, token counts, input/output messages, latency, attributes, status code.
- Span-level detail: full message arrays (role, content), tool calls, retrieved documents with scores.
- **Strength**: Richer span-level detail for RAG pipelines (document relevance scores visible inline).
- Filter by: project, session, time range, span kind, status, annotation labels.

**Sessions:**
```python
from openinference.instrumentation import using_session

with using_session(session_id="user_123_conv_456"):
    response = llm.invoke(prompt)
    # All child spans automatically inherit session_id
```
- OTEL context propagation: `using_session()` injects `session.id` into all nested spans automatically — no manual threading.
- Recognizes: `thread_id`, `session_id`, `conversation_id` from LangChain metadata.
- Session-level annotations: `client.sessions.add_session_annotation(...)`.
- **Limitation**: Session replay is less polished than LangFuse — shows a span list grouped by session, not a conversation-style message timeline.

**Verdict:** LangFuse has the better session replay UX for conversational agents (message timeline). Phoenix has better raw span detail for RAG/tool use inspection. For the Money Coach (multi-turn financial conversation), LangFuse session replay is more meaningful.

---

## 5. OpenTelemetry (OTEL) Support

### LangFuse

**OTEL Ingest:**
- LangFuse accepts OTEL traces via the **OTLP HTTP endpoint**.
- Set `OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel` with Basic Auth headers (public:secret key).
- Maps OTEL semantic conventions to LangFuse data model (trace → trace, span → observation).
- Supports any OTEL-compatible SDK (Python, JS, Go, Java, etc.).

**Proprietary SDK (primary path):**
- `langfuse` Python/JS SDK with `@observe()` decorator and `CallbackHandler` for LangChain — richer metadata than raw OTEL (token costs, prompt versions, scores).
- OTEL support is a **compatibility layer**, not the primary design.

**Limitations:**
- OTEL ingest loses LangFuse-specific features: no automatic prompt version linking, no cost tracking, limited score attribution.
- Not truly OTEL-native — the OTEL endpoint is a mapping shim.
- Cannot receive Phoenix's `openinference.*` semantic convention attributes natively.

---

### Arize Phoenix

**OTEL Native:**
- Phoenix is **built on OpenTelemetry** from the ground up.
- OTLP endpoint: `http://localhost:6006/v1/traces` (gRPC: port 4317, HTTP: port 4318).
- `arize-phoenix-otel` wraps standard OTEL SDK with LLM-specific defaults:
  ```python
  from phoenix.otel import register
  register(project_name="my-app", auto_instrument=True)
  # Sets up BatchSpanProcessor → OTLP exporter → Phoenix
  ```
- **Auto-instrumentation** via `openinference-instrumentation-*` packages:
  - `openinference-instrumentation-openai`
  - `openinference-instrumentation-langchain`
  - `openinference-instrumentation-llama-index`
  - And many more — all zero-code instrumentation.

**OpenInference Semantic Conventions:**
- Superset of OTEL for LLM: defines standard attributes for `llm.input_messages`, `llm.output_messages`, `retrieval.documents`, `tool.parameters`, `session.id`, `user.id`, etc.
- Published open spec: https://github.com/Arize-ai/openinference/tree/main/spec
- Any OpenInference-instrumented app works with Phoenix, LangSmith, and any OTEL backend.

**Batch processing config (OTEL standard env vars):**
```bash
OTEL_BSP_SCHEDULE_DELAY=5000       # Batch every 5s
OTEL_BSP_MAX_QUEUE_SIZE=2048
OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512
```

**Limitations:**
- OTEL-only means less built-in "LangFuse-style" features: no prompt version management, no cost tracking from tokens, no scoring dashboard.
- Custom spans require manual attribute setting per OpenInference spec.
- No HMAC webhook signature for any event emission.

**Verdict:** Phoenix is OTEL-native and the right choice if portability and standard tooling matter. LangFuse's OTEL support is a compatibility shim — it works but you lose rich features. For this project, we use **both** (LangFuse callback for rich features + Phoenix OTEL for distributed tracing portability).

---

## 6. Summary Comparison Table

| Capability | LangFuse | Arize Phoenix | Winner |
|---|---|---|---|
| **Prompt versioning (labels/environments)** | Full label system, rollback, diff view | Basic versioning only, no label routing | **LangFuse** |
| **Runtime prompt serving by label** | `get_prompt(label="production")` | Not supported natively | **LangFuse** |
| **Prompt fallback / guaranteed availability** | Built-in (SDK cache + static file pattern) | Manual implementation required | **LangFuse** |
| **Webhook on prompt change** | Yes — `created/updated/deleted` | None | **LangFuse** |
| **Filter webhook by label** | Not natively — needs middleware | N/A | Neither (LF needs workaround) |
| **GitHub Actions integration** | Built-in Repository Dispatch | None | **LangFuse** |
| **Protected labels (RBAC)** | Pro/Enterprise tier | N/A | **LangFuse** |
| **Dataset creation from traces (bulk)** | SDK only (UI = single trace) | SDK only (UI = single trace) | Tie |
| **Dataset batch-add from observations** | Yes (Observations table batch action) | No | **LangFuse** |
| **LLM-as-judge (server-side, no-code)** | Yes (built-in templates, model picker) | Via `phoenix-evals` (code required) | **LangFuse** |
| **Custom eval scoring API** | Trace + span level scores | Span + trace + doc + session level | **Phoenix** (more granular) |
| **Experiments UI (baseline vs candidate)** | Yes — side-by-side, linked to prompts | Yes — `run_experiment()` | Tie |
| **Session replay (conversation timeline)** | Yes — chronological message replay | Span list grouped by session_id | **LangFuse** |
| **Session annotation** | Trace-level only | Native session-level annotation | **Phoenix** |
| **Trace UI span detail** | Good — model, cost, tokens, tags | Excellent — full message arrays, doc scores | **Phoenix** |
| **OTEL native** | Shim (OTLP ingest, proprietary SDK primary) | Native — built on OTEL | **Phoenix** |
| **Auto-instrumentation (zero-code)** | LangChain callback only | Yes — OpenInference packages for 15+ frameworks | **Phoenix** |
| **OTEL semantic conventions** | Langfuse-proprietary | OpenInference (open spec, vendor-neutral) | **Phoenix** |
| **Multi-language OTEL support** | Python + JS (proprietary); any via OTEL shim | Any OTEL-compatible language | **Phoenix** |
| **Self-hostable** | Yes (Docker Compose / K8s) | Yes (Docker / Cloud) | Tie |
| **Open source** | Yes (GitHub: langfuse/langfuse) | Yes (GitHub: Arize-ai/phoenix) | Tie |

---

## 7. Gap Analysis: Planned Pipeline vs. Both Tools

### The Webhook Filtering Gap (LangFuse)

**Problem (user-reported):** LangFuse webhook `event filter` fires on `created/updated/deleted` but cannot filter "only when label `production` is assigned." Both the version that gains `production` and the one that loses it fire `updated`. This makes raw GitHub dispatch trigger noisy/double.

**Root cause:** LangFuse doesn't emit a distinct `label.assigned` event — it only emits `updated` with the new full label array.

**Required workaround:**
```
LangFuse Webhook (all "updated" events)
    ↓
Cloud Function (GCP Cloud Run / Cloud Functions)
    Filter: action == "updated" AND "production" in prompt.labels
    Extract: prompt_name, version
    ↓
POST https://api.github.com/repos/{owner}/{repo}/dispatches
    { event_type: "langfuse-prompt-update",
      client_payload: { prompt_name, version } }
    ↓
GitHub Actions: prompt-promotion-pipeline.yaml
```

This adds ~1 infra component but keeps the rest of the pipeline clean.

---

### The Dataset-from-Traces Gap (LangFuse)

**Problem (user-reported):** UI only supports adding one trace at a time to a dataset. No "select 50 traces with `assessment_phase=completed` and add them all."

**Current solution in this project:** `evaluation/dataset/seeder.py` — custom `TraceSeeder` class that:
1. Fetches traces via `langfuse.fetch_traces()` with filters
2. Applies eligibility criteria in Python
3. Calls `create_dataset_item()` in a loop

**This is the right approach.** LangFuse's batch-add via the Observations table only works for individual observations/spans, not for constructing dataset items from the full trace context (messages array + metadata). The SDK seeder is the correct architectural pattern.

Phoenix has the same gap — no bulk trace-to-dataset tooling built in.

---

### Phoenix Gaps for This Pipeline

| Gap | Impact |
|---|---|
| No prompt label system | Cannot implement the dev→sit→production label promotion flow |
| No webhooks | Cannot trigger CI/CD on prompt label change |
| No runtime prompt serving by label | Services cannot do `get_prompt(label="production")` |
| No conflict guard between tracks | Dev track and DS track could silently overwrite each other |
| No guaranteed availability / fallback | Services break if Phoenix is down |

**Phoenix is not a replacement for LangFuse** in the planned pipeline. It is complementary as a tracing/eval backend.

---

## 8. Recommended Architecture for This Project

```
PROMPT MANAGEMENT PLANE (LangFuse — primary)
  langfuse-<proj>-nonprod: dev authoring, sit testing
  langfuse-<proj>-prod: canary, production runtime
  Webhook → Cloud Function → GitHub Dispatch (filter middleware)
  GitHub Actions: sync-to-prod → auto-eval → tag-canary

TRACING PLANE (dual — both active)
  LangFuse CallbackHandler:
    - Linked to prompt versions (prompt_name, version tracked per generation)
    - Session replay via sessionId
    - Experiments UI for eval run comparison
    - Scoring: composite + per-dimension scores

  Phoenix OTel (arize-phoenix-otel):
    - Portable OTEL spans for platform-agnostic observability
    - Richer span-level attributes (full message arrays)
    - Session annotations (session-level feedback)
    - Fallback tracing if LangFuse is unavailable

EVAL PLANE (LangFuse datasets + custom SDK judge)
  evaluation/dataset/seeder.py → nonprod LangFuse dataset
  evaluation/runner/graph_factory.py → baseline + candidate graphs
  evaluation/judge/evaluator.py → LLM judge (5 dimensions)
  evaluation/comparison/comparator.py → pass/fail decision
  Scores linked to: traces, dataset run items, Experiments UI
```

---

## 9. Open Issues from the Planned Pipeline (PDF)

| Open Question | Recommendation |
|---|---|
| Should we sync back production prompt to dev/sit? | **No auto-sync.** DS-originated changes in prod should be re-promoted from DS track through nonprod for full audit trail. Manual re-promote is safer than auto-sync. |
| Manual vs Auto sync for prompt fallback | **Auto sync via CI step**: after any label promotion, CI writes `prompt_config.yaml` from the promoted version. This avoids manual copy-paste drift. |
| Alternative: re-promote from dev instead of back-sync | Viable if DS changes are rare. Risk: loses DS-originated improvements if dev promotes a new version on top. Requires communication protocol between teams. |
| Conflict guard implementation | Use LangFuse REST API in the sync job: `GET /api/public/v2/prompts/{name}` from prod project, compare `version` field against nonprod source. Block sync if `prod.version > nonprod.version`. |

---

*Generated: 2026-03-17 | Based on: LangFuse docs (langfuse.com), Phoenix skill rules (OpenInference), project codebase at `/Users/pirayan/Desktop/langfuse-poc`, and planned pipeline PDF.*
