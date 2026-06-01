# MIGRATION_NOTES

Phase 0 ships with deliberate, documented compromises so we can validate the AI
spine end-to-end without infra dependencies that aren't available locally. Each
compromise has a clear migration path.

---

## 1) Mongo → Postgres + pgvector (when scale demands it)

**Current:** All persistence is in MongoDB (`solutions`, `orchestration_runs`).
Mongo is excellent for the heterogeneous, evolving `orchestration_runs.steps[]`
shape and works well for the small Phase-0 catalogue.

**Why migrate eventually:**
* Once the catalogue grows past O(10⁵) solutions or relevance accuracy demands
  hybrid SQL+vector queries (`WHERE category = X AND embedding <-> q < 0.3`),
  Postgres + `pgvector` is the natural fit.
* Multi-tenant analytics over runs is easier in SQL.

**Migration path (sketch):**
1. Introduce a `repositories/` layer that abstracts Mongo access — keep all
   queries behind functions. Today `services/orchestrator.py` and the seed
   script use the motor handle directly; swapping that to a repository pattern
   is a one-day refactor.
2. Stand up Postgres + `pgvector`. Define tables: `solutions` (with
   `embedding vector(3072)`), `orchestration_runs`, `orchestration_steps`.
3. Run a one-time migration: dump Mongo collections → load into Postgres.
   Embeddings are already vectors of float — direct cast to `pgvector`.
4. Replace the repository implementations. No agent or orchestrator code needs
   to change.

---

## 2) Local cosine numpy → Atlas Vector Search (or pgvector ivfflat)

**Current:** `services/vector_index.py` keeps an L2-normalized numpy matrix
of embeddings in memory. `query()` does a single matmul (`O(N·D)`). For N=10
this is microseconds; at N=10⁴ it stays comfortable; at N≥10⁶ it becomes
the bottleneck.

**Why this is a compromise:**
* Local MongoDB cannot use `$vectorSearch` (Atlas-only feature). We considered
  embedded-Elasticsearch / Milvus but they add operational weight not justified
  at Phase 0.
* The numpy index is **not ANN** — it is exact cosine. That is actually a
  benefit for recall correctness; the downside is linear-time queries.
* The index is rebuilt from Mongo on app startup and via `upsert()` after each
  successful `embed_solution` task. There is no persistent index file.

**Migration path:**

Option A — **MongoDB Atlas Vector Search** (closest to existing code):
1. Move the Mongo deployment to Atlas with a vector-search index on
   `solutions.embedding`.
2. Replace `VectorIndex.query()` with a `$vectorSearch` aggregation.
3. Delete the in-process matrix entirely. `vector_index_size` becomes the
   Atlas index doc count.

Option B — **Postgres + pgvector** (if we also do #1):
1. Add `pgvector` extension and an `ivfflat` index on the embedding column.
2. `query()` becomes `SELECT id, 1-(embedding <=> :q) AS cos FROM solutions
   ORDER BY embedding <=> :q LIMIT :k`.

Either way, the `VectorIndex` abstraction stays in code as a thin pass-through
to the new backend — agents (especially `SemanticSearchAgent`) do not need to
change.

---

## 3) BullMQ → Celery (already done)

The original Node ecosystem default was BullMQ. Phase 0 uses Celery + Redis
because the rest of the backend is Python. The contract is equivalent:

| BullMQ concept   | Celery equivalent                  |
| ---------------- | ---------------------------------- |
| Queue            | `task_default_queue="mergent"`     |
| Job              | `apply_async()`                    |
| Worker           | `celery -A celery_app worker`      |
| Retry policy     | `bind=True, max_retries=3, retry`  |
| Backoff          | `default_retry_delay=5`            |
| Deduplication    | Redis `SETNX` lock (see `tasks.py`)|
| Result backend   | `backend=REDIS_URL` (Celery)       |

The Redis broker URL is shared so observability tools (`celery -A ... events`)
work out-of-the-box. Future migration to RQ / Dramatiq / Arq is mechanical.

---

## 4) Provider abstraction

`AIProviderService` uses LiteLLM under the hood — the same library
`emergentintegrations.llm.chat.LlmChat` uses internally. We chose to call
`litellm.acompletion` directly (instead of through `LlmChat`) so that:
* We get raw `usage` for token accounting.
* We have explicit control over `response_format`, `temperature`, and timeouts.
* Failover across providers is implemented at this layer, not duplicated per agent.

If/when the Emergent universal key is replaced with direct provider keys, swap
the `api_key` and `api_base` only; the rest of the code is provider-agnostic.

---

## 5) WebSocket scaling

The in-process `WSManager` is correct and fast for a single backend pod.
At Phase 1+ when we run multiple backend replicas we'll need to:

1. Move the per-run broadcast plane to **Redis Pub/Sub** (one channel per
   `run_id`).
2. Each backend pod publishes step events to Redis; each pod subscribes to the
   channels for runs that have active local WS clients.
3. The replay buffer moves to a short-TTL `LIST` per `run_id` so a late
   subscriber on any pod can replay.

This is a localized change in `services/ws_manager.py`; orchestrator code stays
the same.
