"""MERGENT Phase 0 backend tests — pytest.

Covers:
- /api/health, /api/openapi.json
- POST /api/match validation & 202 latency
- GET /api/match/{run_id}, /api/match/{run_id}/trace
- /api/admin/* endpoints
- WS /api/ws/match/{run_id} streaming (6+ agent_step events + run_completed)
- Canonical textile query — TextileFlow ERP must be in top 3 (3 runs)
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

REQUIRED_AGENTS = {"Intake", "Parser", "Embedding", "SemanticSearch", "ContextCompression", "Ranking"}


def _agents_seen_match(agents_seen: set) -> set:
    """Return required agents that appear as substring in any seen agent name."""
    matched = set()
    for req in REQUIRED_AGENTS:
        for seen in agents_seen:
            if req.lower() in (seen or "").lower():
                matched.add(req)
                break
    return matched


def _textileflow_in_top3(result: list) -> bool:
    """TextileFlow ERP identification: match by explanation text (which includes the name)."""
    for item in result[:3]:
        expl = (item.get("explanation") or "").lower()
        if "textileflow" in expl:
            return True
    return False
TRACE_STEP_FIELDS = {"agent", "status", "started_at", "ended_at", "execution_ms"}
CANONICAL_QUERY = "Inventory management for textile business with vendor portal"


def _poll_run(run_id: str, timeout_s: float = 90.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/match/{run_id}", timeout=10)
        if r.status_code == 200:
            last = r.json()
            if last.get("status") in ("completed", "failed"):
                return last
        time.sleep(1.5)
    raise AssertionError(f"Run {run_id} did not complete in {timeout_s}s. Last status: {last and last.get('status')}")


# ---------------- Health & OpenAPI ----------------
class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["mongo"] == "up"
        assert d["redis"] == "up"
        assert d["celery"] == "up"
        assert d["vector_index_size"] >= 10, f"vector_index_size expected ≥10 (Phase 0 minimum), got {d['vector_index_size']}"

    def test_openapi_schema(self):
        r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("openapi", "").startswith("3.")
        paths = set(d.get("paths", {}).keys())
        for p in ["/api/match", "/api/health", "/api/admin/providers/health",
                  "/api/admin/orchestration/runs", "/api/admin/solutions/reindex"]:
            assert p in paths, f"missing path {p}"


# ---------------- /api/match validation ----------------
class TestMatchValidation:
    def test_empty_string_400(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": ""}, timeout=10)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "empty_requirement"

    def test_whitespace_400(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": "   "}, timeout=10)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "empty_requirement"

    def test_too_short_400(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": "abc"}, timeout=10)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "requirement_too_short"

    def test_too_long_400(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": "a" * 8001}, timeout=10)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "requirement_too_long"

    def test_non_string_422(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": 12345}, timeout=10)
        assert r.status_code in (400, 422), f"got {r.status_code}: {r.text}"


# ---------------- /api/match 202 + latency ----------------
class TestMatchAccept:
    def test_post_match_202_fast(self):
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": CANONICAL_QUERY}, timeout=10)
        latency_ms = (time.time() - t0) * 1000
        assert r.status_code == 202
        body = r.json()
        assert "run_id" in body
        # Allow loose threshold across remote networks (spec is <500ms locally)
        assert latency_ms < 2500, f"POST /match latency {latency_ms:.0f}ms exceeds 2500ms"


# ---------------- Full pipeline: completion, trace, ranking ----------------
class TestPipelineCanonical:
    @pytest.fixture(scope="class")
    def completed_run(self):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": CANONICAL_QUERY}, timeout=10)
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        doc = _poll_run(run_id, timeout_s=120.0)
        assert doc["status"] == "completed", f"run failed: {doc}"
        return doc

    def test_run_completed_has_result(self, completed_run):
        result = completed_run.get("result")
        assert isinstance(result, list) and len(result) >= 3
        for item in result:
            assert "solutionId" in item
            assert 0 <= float(item["score"]) <= 100
            assert "explanation" in item
            assert item.get("confidence") in {"low", "medium", "high"}

    def test_trace_has_all_agents_with_structured_fields(self, completed_run):
        run_id = completed_run["run_id"]
        r = requests.get(f"{BASE_URL}/api/match/{run_id}/trace", timeout=10)
        assert r.status_code == 200
        d = r.json()
        steps = d.get("steps", [])
        agents_seen = {s.get("agent") for s in steps}
        matched = _agents_seen_match(agents_seen)
        missing = REQUIRED_AGENTS - matched
        assert not missing, f"missing agents in trace: {missing} (seen={agents_seen})"
        # Required structured fields validated on completed steps only
        required_fields = {"agent", "status", "started_at", "ended_at", "execution_ms",
                           "provider_used", "token_usage", "ws_emitted_at", "retry_count"}
        completed_steps = [s for s in steps if s.get("status") == "completed"]
        assert len(completed_steps) >= 6, f"expected >=6 completed steps, got {len(completed_steps)}"
        for s in completed_steps:
            for f in required_fields:
                assert f in s, f"completed step {s.get('agent')} missing field {f}"

    def test_textileflow_in_top3_run1(self, completed_run):
        assert _textileflow_in_top3(completed_run["result"]), \
            f"TextileFlow ERP not in top 3: {[r.get('explanation','')[:80] for r in completed_run['result'][:3]]}"


class TestTextileFlowConsistency:
    """Repeat canonical query 2 more times (combined with TestPipelineCanonical = 3 runs)."""

    @pytest.mark.parametrize("attempt", [1, 2])
    def test_textileflow_in_top3_repeated(self, attempt):
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": CANONICAL_QUERY}, timeout=10)
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        doc = _poll_run(run_id, timeout_s=120.0)
        assert doc["status"] == "completed"
        assert _textileflow_in_top3(doc["result"]), \
            f"attempt {attempt}: TextileFlow not in top 3: {[r.get('explanation','')[:80] for r in doc['result'][:3]]}"


# ---------------- WebSocket ----------------
class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_streams_agent_events(self):
        # Start a run
        r = requests.post(f"{BASE_URL}/api/match", json={"requirement_text": CANONICAL_QUERY}, timeout=10)
        assert r.status_code == 202
        run_id = r.json()["run_id"]

        url = f"{WS_BASE}/api/ws/match/{run_id}"
        events = []
        try:
            async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
                end = time.time() + 120
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    except asyncio.TimeoutError:
                        break
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    events.append(msg)
                    if msg.get("type") == "run_completed":
                        break
        except Exception as e:
            pytest.fail(f"WS connection failed: {e}")

        # All events must carry matching run_id
        for ev in events:
            if "run_id" in ev:
                assert ev["run_id"] == run_id, f"run_id mismatch in {ev}"

        agent_steps = [e for e in events if e.get("type") == "agent_step"]
        agents_seen = {e.get("agent") for e in agent_steps}
        assert len(agent_steps) >= 6, f"expected >=6 agent_step events, got {len(agent_steps)}: agents={agents_seen}"
        matched = _agents_seen_match(agents_seen)
        assert REQUIRED_AGENTS == matched, f"missing agents in WS: {REQUIRED_AGENTS - matched} (seen={agents_seen})"
        assert any(e.get("type") == "run_completed" for e in events), "no run_completed event"


# ---------------- Admin endpoints ----------------
class TestAdmin:
    def test_providers_health(self):
        r = requests.get(f"{BASE_URL}/api/admin/providers/health", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "providers" in d
        assert "chain" in d and isinstance(d["chain"], list) and len(d["chain"]) >= 1

    def test_admin_runs_list(self):
        r = requests.get(f"{BASE_URL}/api/admin/orchestration/runs?limit=10", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "runs" in d
        assert isinstance(d["runs"], list)
        assert len(d["runs"]) <= 10

    def test_reindex_enqueue(self):
        r = requests.post(f"{BASE_URL}/api/admin/solutions/reindex", timeout=10)
        assert r.status_code in (200, 503), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 200:
            d = r.json()
            assert d.get("queued") is True
            assert "task_id" in d
