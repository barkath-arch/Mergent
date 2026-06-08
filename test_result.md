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
