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
