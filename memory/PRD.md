# MERGENT — PRD

## Problem statement (verbatim, condensed)

Build MERGENT — an AI-Orchestrated Software Acquisition Ecosystem. Tagline:
*Find. Acquire. Deploy.*

**Phase 0** (scope of this delivery): the AI spine + API. Prove the
orchestrator → agents → WS streaming → ranked results pipeline end-to-end
against a small seeded catalogue. No auth, no UI.

Phase 0 was extended with a Resilience + Observability amendment requiring
structured logging, provider failover, retry/timeout policy, per-run WS
isolation, Redis/Mongo reconnect handling, duplicate-embed prevention,
input validation, health endpoints, and a deterministic ranking invariant.

## Architecture (delivered)

Stack: FastAPI (port 8001) · MongoDB (motor) · Celery + Redis · LiteLLM via
emergentintegrations · native FastAPI WebSocket · JSON structured logging
(python-json-logger).

Pipeline: `Intake → RequirementParser → Embedding → SemanticSearch →
ContextCompression(if needed) → Ranking`.

Embeddings: **local BAAI/bge-base-en-v1.5** (768-dim) via fastembed/ONNX —
the Emergent universal-key proxy currently does **not** expose OpenAI
embedding endpoints, only chat. This is a documented Phase 0 compromise
(see `MIGRATION_NOTES.md`). Cosine similarity is real and exact (numpy).

Catalogue: 10 seeded solutions covering Inventory Management (textile),
HR, CRM, Project Management, E-commerce.

## What's been implemented (2026-02 → 2026-06)

* `/app/backend/services/ai_provider.py` — chat + chat_json + embed with
  provider failover (`AI_PROVIDER_CHAIN`), retry policy, timeouts, token
  accounting, health snapshot, embed cache.
* `/app/backend/services/orchestrator.py` — async pipeline; structured
  per-step records + WS broadcast; concurrency model documented in file
  header; failure path records `error`, broadcasts `run_failed`.
* `/app/backend/services/ws_manager.py` — per-`run_id` channels, replay
  buffer for late subscribers, no cross-talk between runs.
* `/app/backend/services/vector_index.py` — in-memory L2-normalized matrix
  with `query()` / `upsert()` / `rebuild()`.
* `/app/backend/agents/*.py` — Intake, Parser, Embedding, SemanticSearch,
  ContextCompression, Ranking.
* `/app/backend/celery_app.py` + `tasks.py` — `embed_solution`,
  `reindex_all_solutions`, Redis SETNX lock for duplicate prevention.
* `/app/backend/server.py` — `/api/match`, `/api/match/{run_id}`,
  `/api/match/{run_id}/trace`, `/api/ws/match/{run_id}`, `/api/health`,
  `/api/admin/providers/health`, `/api/admin/orchestration/runs`,
  `/api/admin/solutions/reindex`, `/api/openapi.json`. Input validation:
  empty/whitespace/<5/>8000/non-string all rejected with proper codes.
* `/app/backend/scripts/seed_phase0.py` — idempotent 10-solution seed.
* `/app/backend/scripts/consistency_check.py` — 5/5 textile invariant
  (PASS).
* `/app/backend/scripts/concurrency_check.py` — 5 parallel runs (PASS).
* `/app/backend/scripts/failover_check.py` — anthropic→openai fallback
  (PASS).
* `/app/backend/scripts/celery_resilience_check.py` — kill+restart worker,
  jobs recover (PASS).
* Supervisor configs added for `redis` and `celery_worker`.
* `/app/backend/README.md` and `/app/backend/MIGRATION_NOTES.md`.

## Phase 1 unlock gates — status

| Gate                                                         | Status |
| ------------------------------------------------------------ | ------ |
| Semantic relevance consistency (TextileFlow in top 3, 5/5)   | ✅ PASS |
| Streaming integrity under concurrency (5 parallel, no x-talk)| ✅ PASS |
| Provider abstraction reliability (anthropic→openai)          | ✅ PASS |
| Celery resilience (kill+restart, no lost jobs)               | ✅ PASS |

## Prioritized backlog (P0/P1/P2 — for Phase 1+)

* **P0** Replace local embeddings with OpenAI `text-embedding-3-large`
  once an embedding-capable key is available (or move to Atlas vector search).
* **P0** Add auth (JWT-based custom auth OR Emergent Google login) on the
  `/api/admin/*` endpoints currently marked TODO.
* **P0** Build the Phase 1 UI: requirement input → live trace stream →
  ranked results grid with explanations.
* **P1** Builder/seller-side onboarding and a write-side API to add
  solutions to the catalogue.
* **P1** Per-user run history with filtering and rerun.
* **P1** Stripe-based marketplace transaction flow (acquire).
* **P2** Atlas Vector Search migration (drop the in-memory numpy matrix).
* **P2** WS scaling via Redis Pub/Sub (for multi-replica deploy).
* **P2** Postgres + pgvector option (covered in MIGRATION_NOTES).

## Acceptance criteria — final status

| Criterion                                                         | Status |
| ----------------------------------------------------------------- | ------ |
| A — POST /api/match returns {run_id} <500ms                       | ✅ ~2ms |
| B — WS streams ≥5 step events                                     | ✅ 6 + run_completed |
| C — Result has ≥3 entries with required fields                    | ✅ 10  |
| D — TextileFlow ERP in top 3 for textile query                    | ✅ 5/5 |
| E — AI_PROVIDER=anthropic completes the same query                | ✅      |
| F — /api/openapi.json valid OpenAPI 3                             | ✅ 7 paths |
| G — Celery logs show embed_solution per seeded solution           | ✅      |
| Structured trace per step (logging amendment)                     | ✅      |
| Provider failover with fallback_event                             | ✅      |
| 5 concurrent runs without WS cross-talk                           | ✅      |
| Mongo + Redis reconnect resilience                                | ✅      |
| Duplicate-embedding lock (Redis SETNX)                            | ✅      |
| Malformed input handling                                          | ✅      |

## Known compromises

1. **Embeddings are local (BAAI/bge-base-en-v1.5)**, not OpenAI
   `text-embedding-3-large`. The Emergent universal-key proxy did not expose
   any embedding model at build time. The architecture is provider-agnostic;
   a one-line swap restores OpenAI when an embedding-capable key is supplied.
   Real semantic search, not mocked vectors. See `MIGRATION_NOTES.md`.

2. **Vector index is in-process numpy**, not Atlas Vector Search (local
   Mongo doesn't support `$vectorSearch`). Exact cosine, sub-second at
   N=10⁴; documented migration path to Atlas / pgvector.
