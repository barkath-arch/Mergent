# Test Results

## Phase R — Restoration & Hardening

- Status: <pending tester verification>

### Acceptance Criteria

- [ ] Backend boots, `/api/health` green (mongo + redis + celery all `up`,
      providers populated, vector_index_size > 0 after seed)
- [ ] supervisor: backend, frontend, mongodb, redis, celery_worker, celery_beat
      all RUNNING (mobile is best-effort — ngrok tunnel may flake; not a Phase R
      blocker)
- [ ] `/api/admin/*` returns 401 without auth, 403 with non-admin token,
      200 with admin token (paths: `solutions/reindex`, `orchestration/_debug`,
      `providers/health`, `orchestration/runs`)
- [ ] `POST /api/match` with `{"requirement_text":"I need a SaaS billing
      dashboard for SMB e-commerce"}` returns `{run_id}` (HTTP 202);
      WS stream on `/api/ws/match/{run_id}` emits 6 `agent_step` events and
      a `run_completed`; `GET /api/match/{run_id}` shows
      `status=completed` and `result` length > 0
- [ ] All three seed users log in successfully
      (`buyer@example.com`, `builder@example.com`, `admin@example.com`)
      with the passwords documented in `/app/memory/test_credentials.md`
- [ ] `db.solutions.count_documents({}) > 0` and
      `db.solutions.count_documents({embedding: {$exists: true, $ne: []}})`
      equals the total count

## Phase AGENTS — Step 1 (Foundation)

- Status: <pending tester verification>

### Acceptance Criteria

- [ ] `provider_chain` includes `groq` when `AI_PROVIDER_CHAIN` is set to
      include it; default chain remains `openai,anthropic,gemini`. Groq is
      opt-in: when `GROQ_API_KEY` is set the direct path is used, otherwise
      the call is attempted via the Emergent proxy.
- [ ] After a single `POST /api/match` run, `db.ai_usage_logs` has ≥ 2
      documents (1 chat from RequirementParserAgent + 1 chat from RankingAgent
      + 1 embed from EmbeddingAgent on a cache miss; cached runs may have 2).
      Each doc has `provider`, `model`, `agent_name`, `tokens_in`,
      `tokens_out`, `total_tokens`, `latency_ms`, `cost_usd`, `success`.
- [ ] After a single `POST /api/match` run, `db.agent_runs` has exactly 6
      documents (one per agent), each with `agent_name`, `agent_version`,
      `run_id`, `success`, `duration_ms`, `input_json`, `output_json`,
      `started_at`, `created_at`.
- [ ] `db.match_runs.find_one({_id: run_id})` returns a doc with `buyer_id`
      field present (null or actual id when caller authenticated or supplied).
- [ ] `POST /api/match` with `{"requirement_text":"I need a CRM for my sales
      team","buyer_id":"test"}` returns `{"run_id":"<uuid-like>"}` and the
      `match_runs` doc has `buyer_id: "test"`.
- [ ] WS at `/api/ws/match/{run_id}` streams ≥ 6 `agent_step` events with a
      human-readable `message` field. Expected sequence (12 + 1 synthetic):
      Intake/Parser running/done × "Understanding…",
      Embedding/Search running/done × "Searching…",
      Compression running/done × "Validating…",
      Ranking running/done × "Scoring…",
      Orchestrator running × "Preparing…", then `run_completed`.
- [ ] `GET /api/match/{run_id}` returns `status: completed` and `result`
      length > 0 within ~30 s on a 10-solution catalogue.
- [ ] `/api/admin/orchestration/runs` (admin-gated) returns recent runs read
      from `match_runs`. Returned shape: `{"runs": [...]}`.
- [ ] Pytest baseline: `tests/test_match_integrity.py` + `tests/test_scenarios.py`
      runs at least the 6 logic tests we depend on
      (`test_ranking_prompt_has_no_trust_score_field`,
       `test_compression_prompt_has_no_trust_score`,
       `test_search_payload_has_no_trust_score`,
       `TestUnknownRun::test_unknown_run_returns_404`,
       `TestRankingDeterminism::test_top5_deterministic`,
       `TestContextCompressionKeywords::test_keywords_preserved_after_compression`).
      Pre-existing failures NOT in scope of this step:
      - `test_match_integrity::Test*` (the 3 tests) — log in as the demo
        user `rohit@mergent.demo` which is never seeded; also hits the
        pre-existing `is_locked_out` tz-naive vs tz-aware comparison bug in
        `/app/backend/auth.py:185` (separate auth-debt ticket).
      - `TestDebugEndpoint::test_debug_shape` — written against the Phase 0
        unauthenticated `/api/admin/orchestration/_debug`. Phase R intentionally
        gated this to admin; the test must be updated to inject an admin token.

## Testing Protocol

- Read `/app/memory/test_credentials.md` for credentials and auth injection
  patterns. Use those exact values.
- Backend testing: invoke `deep_testing_backend_v2` first; do NOT invoke
  frontend testing without explicit user permission.
- When updating this file, never edit the **Testing Protocol** section.
- Always update this file before re-invoking a testing agent so it has fresh
  acceptance criteria.
- Stripe + Resend stay on the simulated fallback paths for Phase R. Tests must
  not assume real payment / email delivery; they must accept the
  `simulated_checkout: true` and `[SIMULATED] email_send` signals as
  correct-behavior markers.

## Incorporate User Feedback

- Phase R is restoration-only. No new features. If the testing agent reports a
  gap that is not in the Acceptance Criteria above, the main agent should
  surface it back to the user before patching.
- Match-pipeline tests must use a real EMERGENT_LLM_KEY round-trip — do not
  mock the LLM. If providers return an error, treat that as a real failure
  (not a test issue) and re-run after checking `/api/admin/providers/health`.

## Communication Log

- Main agent (Phase R initial): backend env restored, indexes added,
  /api/admin/* gated to admin, redis + celery_worker + celery_beat
  supervised, seed catalogue + seed users run. Awaiting tester verification.

- Main agent (Phase AGENTS Step 1 fix-up):
  - **Defect 1 (buyer_id missing in GET response)** — ROOT CAUSE:
    `_serialize_run()` in `/app/backend/server.py:322` was omitting the
    `buyer_id` field from its returned dict. The field WAS being written
    to Mongo correctly (confirmed via `match_runs.find_one()`). Fix: added
    `"buyer_id": doc.get("buyer_id")` and `"error": doc.get("error")`
    to `_serialize_run`. Verified: authed POST → response now has
    `buyer_id == current_user.id`; anonymous POST → response has
    `buyer_id: null` (field present).
  - **Defect 2 (redis/celery DOWN in /api/health)** — ROOT CAUSE: container
    pod restarted between Phase R completion and tester run, which wiped
    `/usr/bin/redis-server` (only `/app` persists). Supervisor logged
    `redis FATAL: can't find command '/usr/bin/redis-server'`. The
    Celery worker stayed in RUNNING state but couldn't reach the broker,
    so the backend's `/api/health` Celery ping timed out and reported
    `celery: "down"`. Fix: created `/app/bin/start-redis.sh` (1 KB shell
    wrapper) that `apt-get install`s `redis-server` if missing, then
    execs it. Updated `/etc/supervisor/conf.d/supervisord_phase_r.conf`
    to point `[program:redis]` at the wrapper. `supervisorctl reread &&
    update && restart redis celery_worker celery_beat` brought all 7
    services back. `/api/health` now reports `redis: "up"`, `celery: "up"`.
  - **Defect 3 (WS public→internal 307 redirect)** — VERIFIED tester-tool
    artifact only. Frontend (`/app/frontend/src/lib/api.js:10-12`)
    constructs `WS_BASE` from `window.location.origin` when the page is
    served from `*.emergentagent.com`, so the browser never sees the
    redirect. Mobile uses the same pattern via `EXPO_PUBLIC_BACKEND_URL`.
    Documented under "Known testing-environment quirks" above with
    guidance for running the Python `websockets` lib (use
    `ws://localhost:8001/...` from inside the pod, or use a browser
    context that auto-follows redirects).

## Known testing-environment quirks (not application bugs)

- **WS public→internal 307 redirect.** A direct `wss://github-deploy-hub-1.preview.emergentagent.com/api/ws/match/{run_id}` connection initiated from outside the cluster (e.g. the Python `websockets` library) receives a `307 Temporary Redirect` to the internal preview host. **This is a tester-tool artifact only.** Browser clients (web frontend on the public preview origin, Expo on the same `EXPO_PUBLIC_BACKEND_URL`) construct `wss://` URLs from `window.location.origin` / the configured backend URL and stay same-origin, so they never trigger the redirect — verified in `/app/frontend/src/lib/api.js:10-12` (`WS_BASE = BACKEND.replace(/^http/i, "ws") + "/api/ws"`) where `BACKEND` defaults to the live origin when running on `*.emergentagent.com`. Tester guidance: when validating WS with the Python `websockets` lib, connect via `ws://localhost:8001/api/ws/match/{run_id}` from inside the pod (same-pod localhost — no ingress in the path), or use `httpx`/`Playwright` browser context (which auto-follows the redirect).

- **Self-healing Redis.** The `redis-server` binary lives in `/usr/bin` which is wiped on container restart. Supervisor program `[program:redis]` now invokes `/app/bin/start-redis.sh` (a 1-KB shell wrapper) which `apt-get install`s `redis-server` if `/usr/bin/redis-server` is missing, then `exec`s it. Net effect: Redis survives pod restarts without manual intervention.
