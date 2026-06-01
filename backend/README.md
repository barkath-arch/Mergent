# MERGENT — Phase 0

> **Find. Acquire. Deploy.**
> AI-Orchestrated Software Acquisition Ecosystem.

Phase 0 is the **AI spine + API**: a multi-agent orchestrator that turns a free-text software requirement into ranked solution candidates from a seeded catalogue. No UI, no auth — just the pipeline, streaming over WebSocket, with structured tracing and provider failover.

---

## Stack

| Layer       | Tech                                                  |
| ----------- | ----------------------------------------------------- |
| API         | FastAPI (async, port 8001, all routes under `/api`)   |
| DB          | MongoDB (motor async driver)                          |
| Queue       | Celery + Redis                                        |
| LLM         | `emergentintegrations` + LiteLLM (Emergent proxy)     |
| Embeddings  | OpenAI `text-embedding-3-large` (3072-dim)            |
| Streaming   | Native FastAPI WebSocket                              |
| Logging     | JSON-formatted records (`python-json-logger`)         |

---

## Environment variables

| Var                  | Default                              | Purpose                                              |
| -------------------- | ------------------------------------ | ---------------------------------------------------- |
| `MONGO_URL`          | (existing)                           | Mongo connection string                              |
| `DB_NAME`            | (existing)                           | Database name                                        |
| `EMERGENT_LLM_KEY`   | (provisioned)                        | Universal key for OpenAI / Anthropic / Gemini        |
| `AI_PROVIDER`        | `openai`                             | Primary LLM provider                                 |
| `AI_PROVIDER_CHAIN`  | `openai,anthropic,gemini`            | Failover order (comma-separated)                     |
| `EMBEDDING_MODEL`    | `text-embedding-3-large`             | Embedding model name                                 |
| `REDIS_URL`          | `redis://localhost:6379/0`           | Celery broker + result backend                       |
| `LLM_CHAT_TIMEOUT_S` | `30`                                 | Chat call timeout                                    |
| `LLM_EMBED_TIMEOUT_S`| `15`                                 | Embedding call timeout                               |

---

## Running

Supervisor manages `redis`, `celery_worker`, `backend`, `mongodb`, and `frontend`. Phase 0 only needs the first four.

```bash
sudo supervisorctl status
# expect: backend, celery_worker, mongodb, redis  — all RUNNING
```

Seed the catalogue (idempotent — re-running it is safe):

```bash
cd /app/backend
python -m scripts.seed_phase0
```

Run the canonical consistency check (5 passes against the textile query):

```bash
cd /app/backend
python -m scripts.consistency_check
```

---

## API surface (all `/api`)

| Method | Path                                  | Description                                          |
| ------ | ------------------------------------- | ---------------------------------------------------- |
| POST   | `/api/match`                          | `{requirement_text}` → `{run_id}` (202)              |
| GET    | `/api/match/{run_id}`                 | Full run doc (steps + result if completed)           |
| GET    | `/api/match/{run_id}/trace`           | Structured trace (steps[] with timings / tokens)     |
| WS     | `/api/ws/match/{run_id}`              | Streams per-step events; supports replay buffer      |
| POST   | `/api/admin/solutions/reindex`        | Kicks Celery reindex; 503 fast on queue unavailable  |
| GET    | `/api/admin/providers/health`         | Latest health snapshot per provider                  |
| GET    | `/api/admin/orchestration/runs`       | Recent run summaries (default limit=20)              |
| GET    | `/api/health`                         | Mongo/Redis/Celery/provider health + vector index sz |
| GET    | `/api/openapi.json`                   | OpenAPI 3 schema (auto by FastAPI)                   |

---

## Quick curl examples

```bash
# 1) Submit a match request
curl -s -X POST "$REACT_APP_BACKEND_URL/api/match" \
  -H 'Content-Type: application/json' \
  -d '{"requirement_text":"Inventory management for textile business with vendor portal"}'
# {"run_id":"abc-123-..."}

# 2) Poll the run
curl -s "$REACT_APP_BACKEND_URL/api/match/abc-123-..."

# 3) Structured trace
curl -s "$REACT_APP_BACKEND_URL/api/match/abc-123-.../trace" | jq

# 4) Health
curl -s "$REACT_APP_BACKEND_URL/api/health" | jq
```

WebSocket (with `websocat`):

```bash
websocat "${REACT_APP_BACKEND_URL/https/wss}/api/ws/match/abc-123-..."
# Streams JSON events: agent_step (started → completed), provider_fallback, run_completed
```

---

## Orchestration pipeline

```
Intake → Parser → Embedding → SemanticSearch → ContextCompression(if needed) → Ranking
```

Each step:

* Appends a structured record to `orchestration_runs.steps[]` with `started_at`, `ended_at`, `execution_ms`, `provider_used`, `token_usage`, `retry_count`, `fallback_event`, optional `retrieval_latency_ms` / `rerank_latency_ms`, and `ws_emitted_at`.
* Emits a WS event scoped to `run_id` only (no global broadcast).

---

## Resilience features

* **Provider failover** — `AIProviderService` tries the providers in `AI_PROVIDER_CHAIN` order. Failures are logged and the next provider is attempted. A `fallback_event` is recorded on the step.
* **Retry policy** — 1 retry on transient chat errors (timeout / 5xx / rate-limit), 2 retries on embed (0.5s, 1.5s), 1 JSON-self-correction retry for JSON-mode failures.
* **Per-run WS isolation** — `WSManager` keeps a `dict[run_id, channel]` — subscribers to run A never see events for run B. Buffered replay lets late subscribers see the full event sequence.
* **Redis reconnect** — Celery is configured with `broker_connection_retry_on_startup=True` and `broker_connection_max_retries=None`. `/api/admin/solutions/reindex` returns 503 fast if Redis is unreachable.
* **Mongo reconnect** — motor uses `serverSelectionTimeoutMS=5000` + `retryWrites=True`; critical writes wrap with a 1-retry helper.
* **Duplicate embedding prevention** — Redis `SETNX embed:lock:{id}` with 5-min TTL is acquired before enqueue and validated at task-start.
* **Determinism** — Ranking call uses `temperature=0` with stable cosine-similarity tiebreaker, so the textile invariant (TextileFlow ERP in top 3) holds 5/5.

---

## Inspecting Celery

```bash
tail -f /var/log/supervisor/celery.err.log
```

You should see `Task tasks.embed_solution[...] received` and `succeeded` lines once per seeded solution.

---

## Acceptance test (manual)

```bash
# 1) Seed + embed
python -m scripts.seed_phase0

# 2) Health
curl -s "$REACT_APP_BACKEND_URL/api/health" | jq

# 3) Consistency
python -m scripts.consistency_check     # expect: 5/5 PASS

# 4) Switch providers and re-run
sudo sed -i 's/^AI_PROVIDER=.*/AI_PROVIDER=anthropic/' /app/backend/.env
sudo sed -i 's/^AI_PROVIDER_CHAIN=.*/AI_PROVIDER_CHAIN=anthropic,openai,gemini/' /app/backend/.env
sudo supervisorctl restart backend celery_worker
python -m scripts.consistency_check     # expect: 5/5 PASS (anthropic primary)
```

---

## See also

* `MIGRATION_NOTES.md` — Mongo→Postgres+pgvector, local-cosine→Atlas, BullMQ→Celery
* `services/orchestrator.py` — concurrency model documented at the top of the file
