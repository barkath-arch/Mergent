# MERGENT — PRD (living tracker)

> **Find. Acquire. Deploy.** — AI-Orchestrated Software Acquisition Ecosystem.

This file is the canonical, living tracker. The original Phase 0 + V1.6
history is preserved below; the top sections reflect current truth.

---

## Current Status (as of Phase R)

### Live (real code, real behaviour)

- **Phase 0 — AI spine**: `Intake → RequirementParser → Embedding →
  SemanticSearch → ContextCompression → Ranking`, streamed over
  `/api/ws/match/{run_id}`, structured trace persisted to
  `orchestration_runs`. Provider chain: openai → anthropic → gemini via the
  Emergent universal LLM key.
- **Phase 1 — Auth (JWT)**: register / login / refresh / logout / me /
  verify-email / forgot-password / reset-password. Bcrypt + Redis-backed
  refresh-jti registry + Mongo-backed brute-force throttle.
- **V1.6 — Trust & Quality Agent**: 6-component weighted builder score
  (uptime + tx success + reviews + response + volume/tenure − disputes),
  persisted to `builder_profiles.trust_score`, nightly Celery beat at 03:00 UTC.
- **Phase 6 — Builder Hub**: `/api/me/sales`, `/me/earnings`, `/me/stats`,
  `/me/overview`, `/builders/{id}/trust`. Web Builder Hub UI wired.
- **Phase 7 — Notifications, Saved Items, Audit**: in-app + email (debounced)
  + preferences + one-click unsubscribe; saved items + bulk-exists; per-user
  and admin audit views.
- **Marketplace + Solutions + Requirements**: hybrid keyword+vector search,
  trending, overview, recent requirements, solution CRUD with
  Celery-embed dispatch.
- **Messaging**: REST + WS conversations (per-user channel, unread badge).
- **Transactions / Escrow / Reviews**: state machine `initiated → funded →
  in_progress → delivered → released → reviewed` with match-integrity
  enforcement against the originating run's top-1.
- **Deployments**: per-deployment WS log stream + 7-step FSM with rollback /
  redeploy actions (simulated infra, real state machine).
- **Phase R additions** (this iteration): unique-email + TTL + compound
  indexes on Mongo collections; `/api/admin/*` admin-gated; Redis +
  celery_worker + celery_beat running under supervisor; 3 seed users for testers.
- **Phase AGENTS — Step 1 (Foundation)** additions:
  - `BaseAgent` class hierarchy (`/app/backend/agents/base.py`); the 6
    existing pipeline agents (Intake / RequirementParser / Embedding /
    SemanticSearch / ContextCompression / Ranking) now subclass `BaseAgent`
    while keeping the module-level `run(ctx)` shim so the orchestrator's
    static PIPELINE keeps working.
  - `db.agent_runs` collection: one document per agent execution, capturing
    `agent_name`, `agent_version`, `run_id`, sanitized input/output JSON,
    duration, success/error. 30-day TTL.
  - `db.ai_usage_logs` collection: one document per LLM/embed call,
    capturing `kind` (chat|embed), `provider`, `model`, `agent_name`,
    `tokens_in`, `tokens_out`, `total_tokens`, `latency_ms`, `cost_usd`
    (rough estimate via per-provider lookup table), `success`, `error`.
    30-day TTL.
  - `AIProviderService` extended: `groq` registered as 4th provider
    (opt-in via `AI_PROVIDER_CHAIN`); uses direct Groq API when
    `GROQ_API_KEY` is set, else attempts the Emergent proxy. Default chain
    stays `openai,anthropic,gemini`. `chat()` / `chat_json()` / `embed()`
    now accept an optional `agent_name` kwarg flowed into `ai_usage_logs`.
  - Orchestrator collection rename: `orchestration_runs` → `match_runs`
    (one-time copy migration in `db.ensure_indexes()`; legacy collection
    preserved for rollback). New field `buyer_id` on every run doc;
    auto-filled from the Bearer token when the caller is authenticated.
  - Orchestrator now emits additional human-readable `agent_step` WS events
    with `{event, agent, status: "running"|"done", message}` for 6 agents
    (paired) + a synthetic `"Preparing your recommendations..."` event
    before `run_completed`. Legacy detailed events preserved (additive).

### Stubbed / Simulated (works end-to-end but with documented short-circuits)

- **Stripe checkout** — real call when `STRIPE_API_KEY` is set; otherwise
  `simulated_checkout: true` flips tx to `funded` immediately
  (`transactions_routes.py:127-146`). **Phase R: empty key → simulated path.**
- **Stripe Connect payouts** — not wired. Release credits
  `builder_profiles.earnings_usd` only. UI shows "payout_provider_status:
  simulated" (deferred to Phase 10).
- **Resend email** — real call when `RESEND_API_KEY` is set; otherwise
  `[SIMULATED] email_send` log + `fallback: true` returned
  (`services/email.py:188-194`). **Phase R: empty key → simulated path.**
- **Deployment infrastructure** — the 7-step FSM is `asyncio.sleep`-driven
  fake log lines. `simulated_infra: true` on every deployment doc.
- **Forking** — `POST /api/solutions/{id}/fork` is an **HTTP 501 stub**.
  Validates parent + emits `would_fork` lineage preview; no persistence.
- **Google OAuth** — only `GET /api/auth/google/status` returning the env
  flag. No callback, no real flow.
- **Embeddings** — local `BAAI/bge-base-en-v1.5` via fastembed (the Emergent
  proxy does not expose embedding endpoints). Real semantic vectors, in-process
  numpy index, exact cosine.

### Not started (next phases — see ledger)

- Master Orchestrator (LLM-driven planner with reflection / replan).
- Shared agent memory + agent-to-agent bus.
- Vision Intelligence agents (UI / UX / QA / Security / A11y / Performance).
- Technical Preview (Request Technical Access, sandbox demo levels).
- Real Forking with lineage tracking + royalty split.
- Per-user run history + rerun.
- Mobile Builder Hub / Saved / Notification Settings parity.
- MFA / change-password while logged in.
- OpenAI `text-embedding-3-large` swap.
- Atlas Vector Search / pgvector migration.
- WS scaling via Redis Pub/Sub.

---

## Phase Ledger

| Phase | Goal                                                       | Status      |
| ----- | ---------------------------------------------------------- | ----------- |
| 0     | AI spine + API, structured tracing, provider failover      | done        |
| 1     | JWT auth, profiles, marketplace, solutions, requirements   | done        |
| 6     | Builder Hub + Trust & Quality Agent (V1.6)                 | done        |
| 7     | Notifications + Saved Items + Audit                        | done        |
| 9     | Forking (real) — lineage primitives migrated, route stub   | 501 stub    |
| 10    | Stripe Connect real payouts                                | not started |
| R     | Restoration & Hardening: env + indexes + admin auth + seed | done        |
| AGENTS-S1 | Agents foundation: BaseAgent + ai_usage_logs + agent_runs + match_runs | done |
| A     | Decide & deliver: ONE of {Real Forking, Tech Preview, Run history} | planned |
| B     | Master Orchestrator scaffold + reflection loop (1 agent)   | planned     |
| C     | Vision Intelligence agents (UI/UX/Security/A11y/Perf)      | planned     |
| D     | Production swaps: OpenAI embeddings, Atlas Vector, Redis Pub/Sub, real Stripe Connect | planned |

---

## Open Decisions (to confirm with user)

1. **Embeddings stay local** for now (BAAI/bge-base-en-v1.5). Swap to OpenAI
   `text-embedding-3-large` is gated on the Emergent universal key exposing an
   embedding endpoint OR a separate real OpenAI key being provided. Phase D.
2. **Real Stripe + real Resend** stay deferred. Both fall back to clean
   simulated paths when keys are missing. No customer money or email is sent
   in Phase R.
3. **MFA + change-password (logged-in)** deferred until after Phase A.
4. **Mobile parity gaps** — Builder Hub, Saved, NotificationSettings have no
   mobile screens. Decision needed: build mobile parity or de-scope Builder
   workflows from mobile?
5. **Next big move (Phase A)** — user picks ONE of:
   - **A1**: Implement real Forking (replace 501 stub, persist lineage, fork-tree UI)
   - **A2**: Build Technical Preview (Request Technical Access + sandbox demo levels)
   - **A3**: Add per-user Run history + filter + rerun (the most-cited PRD P1)

---

## Phase R — What changed (this iteration)

- `/app/backend/requirements.txt`: added `resend==2.4.0`.
- `/app/backend/.env`, `/app/frontend/.env`, `/app/mobile/.env`: restored.
- `/app/backend/server.py`: imported `auth.require_role`, gated
  `POST /api/admin/solutions/reindex`, `GET /api/admin/orchestration/_debug`,
  `GET /api/admin/providers/health`, `GET /api/admin/orchestration/runs`.
- `/app/backend/db.py::ensure_indexes()`: added unique-email,
  TTL (email/password reset/login_attempts), compound (messages,
  notifications, saved_items), and per-FK indexes (reviews, transactions,
  conversations).
- `/etc/supervisor/conf.d/supervisord_phase_r.conf`: added programs
  `redis`, `celery_worker`, `celery_beat`.
- `/app/backend/scripts/seed_users.py`: new idempotent seed for 3 test
  accounts (buyer/builder/admin) + matching profile rows.
- `/app/memory/test_credentials.md`: created with credentials and Playwright
  / curl auth-injection examples.
- `/app/test_result.md`: created with Phase R acceptance criteria.

---

## Acceptance Criteria — Phase 0 (kept for history, all ✅)

| Criterion                                                         | Status |
| ----------------------------------------------------------------- | ------ |
| A — POST /api/match returns {run_id} <500ms                       | ✅ ~2ms |
| B — WS streams ≥5 step events                                     | ✅ 6 + run_completed |
| C — Result has ≥3 entries with required fields                    | ✅ 10  |
| D — TextileFlow ERP in top 3 for textile query                    | ✅ 5/5 |
| E — AI_PROVIDER=anthropic completes the same query                | ✅      |
| F — /api/openapi.json valid OpenAPI 3                             | ✅ 8 paths |
| G — Celery logs show embed_solution per seeded solution           | ✅      |
| Structured trace per step                                         | ✅      |
| Provider failover with fallback_event                             | ✅      |
| 5 concurrent runs without WS cross-talk                           | ✅      |
| Mongo + Redis reconnect resilience                                | ✅      |
| Duplicate-embedding lock (Redis SETNX)                            | ✅      |
| Malformed input handling                                          | ✅      |
| ContextCompression engages on long input + preserves keywords     | ✅      |
| WS channels freed on subscriber disconnect (no leak)              | ✅      |

## Known compromises (documented)

1. **Embeddings are local** (`BAAI/bge-base-en-v1.5`), not OpenAI
   `text-embedding-3-large`. The Emergent proxy did not expose any embedding
   model at build time. Real cosine similarity, not mocked. See
   `MIGRATION_NOTES.md`.
2. **Vector index is in-process numpy** — sub-second at N=10⁴, documented
   migration path to Atlas / pgvector.
3. **WS channels persist until at least one subscriber connects+disconnects.**
   Acceptable for Phase 0; a finished+empty TTL sweep is on the Phase D list.
