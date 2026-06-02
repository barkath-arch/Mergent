"""MERGENT Phase 0 — scenario tests (iteration 2).

Covers:
- 404 on unknown run
- WS late-subscriber replay + run_already_finished
- Concurrent stability (no cross-run leakage)
- WS event ordering (monotonic ts, started < completed)
- Canonical textile consistency across 5 runs (top-3 overlap >=2)
- Trace integrity (WS event order mirrors trace.steps)
- ContextCompression keyword preservation on 6000+ char payload
- Ranking determinism (top-5 stable across 2 runs)
- WS channel cleanup (no leak after disconnect)
- Latency p95 across 10 runs (<30s on RankingAgent.rerank_latency_ms)
- Invalid payload isolation alongside valid runs
- /api/admin/orchestration/_debug introspection shape
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

CANONICAL = (
    "We are a textile manufacturer in Surat needing an inventory + ERP system "
    "that handles fabric SKUs, batch dyeing, and supplier POs"
)
TEXTILE_ID = "1923bfa7-ee64-4d7d-9930-9337420329d4"
REQUIRED_AGENTS = ["Intake", "Parser", "Embedding", "SemanticSearch", "ContextCompression", "Ranking"]


def _post_match(text: str, timeout: float = 10):
    return requests.post(f"{BASE_URL}/api/match", json={"requirement_text": text}, timeout=timeout)


def _poll(run_id: str, timeout_s: float = 120.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/match/{run_id}", timeout=10)
        if r.status_code == 200 and r.json().get("status") in ("completed", "failed"):
            return r.json()
        time.sleep(1.0)
    raise AssertionError(f"Run {run_id} did not complete in {timeout_s}s")


def _trace(run_id: str) -> dict:
    r = requests.get(f"{BASE_URL}/api/match/{run_id}/trace", timeout=10)
    assert r.status_code == 200
    return r.json()


def _matches_agent(seen: str, target: str) -> bool:
    return target.lower() in (seen or "").lower()


# ---------------------------------------------------------------------------
class TestUnknownRun:
    def test_unknown_run_returns_404(self):
        bogus = str(uuid.uuid4())
        r = requests.get(f"{BASE_URL}/api/match/{bogus}", timeout=10)
        assert r.status_code == 404
        body = r.json()
        # detail wrapper or top-level error
        err = body.get("detail", body)
        if isinstance(err, dict):
            assert err.get("error") == "run_not_found", f"got {body}"
        else:
            assert "run_not_found" in str(body)


# ---------------------------------------------------------------------------
class TestDebugEndpoint:
    def test_debug_shape(self):
        r = requests.get(f"{BASE_URL}/api/admin/orchestration/_debug", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "ws" in d
        assert {"total_channels", "total_connections", "per_run"} <= set(d["ws"].keys())
        assert isinstance(d.get("provider_chain"), list)
        assert "vector_index_size" in d
        assert "ts" in d


# ---------------------------------------------------------------------------
class TestWSLateSubscriber:
    @pytest.mark.asyncio
    async def test_late_subscriber_gets_replay_and_finished_notice(self):
        # Fire a run and wait for it to fully complete
        r = _post_match(CANONICAL)
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        doc = _poll(run_id, timeout_s=120)
        assert doc["status"] == "completed"
        # Now connect WS after completion
        url = f"{WS_BASE}/api/ws/match/{run_id}"
        events = []
        async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
            try:
                # collect events for up to 8s
                end = time.time() + 8
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=3)
                    except asyncio.TimeoutError:
                        break
                    events.append(json.loads(raw))
            except Exception:
                pass
        types = [e.get("type") for e in events]
        assert any(t == "run_already_finished" for t in types), f"expected run_already_finished, got types={types}"
        assert any(t == "run_completed" for t in types), f"expected replay of run_completed, got {types}"
        assert sum(1 for t in types if t == "agent_step") >= 5, f"expected replay of agent_step events, got {types}"


# ---------------------------------------------------------------------------
class TestInvalidPayloadIsolation:
    """SCENARIO #12 — interleave 5 valid + 5 bad requests, all bad 4xx, all valid completes."""

    def test_interleaved_valid_and_invalid(self):
        bad_payloads = [
            {"requirement_text": ""},
            {"requirement_text": "   "},
            {"requirement_text": "abc"},
            {"requirement_text": "a" * 9000},
            {"not_a_field": "x"},
        ]
        valid_runs = []
        bad_codes = []

        def fire_valid():
            r = _post_match(CANONICAL)
            assert r.status_code == 202
            return r.json()["run_id"]

        def fire_bad(p):
            r = requests.post(f"{BASE_URL}/api/match", json=p, timeout=10)
            return r.status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = []
            for i in range(5):
                futs.append(("valid", pool.submit(fire_valid)))
                futs.append(("bad", pool.submit(fire_bad, bad_payloads[i])))
            for tag, f in futs:
                if tag == "valid":
                    valid_runs.append(f.result())
                else:
                    bad_codes.append(f.result())

        for c in bad_codes:
            assert 400 <= c < 500, f"bad request must be 4xx, got {c}"
        for rid in valid_runs:
            doc = _poll(rid, timeout_s=180)
            assert doc["status"] == "completed", f"run {rid} did not complete: {doc.get('status')}"


# ---------------------------------------------------------------------------
class TestConcurrentStability:
    """SCENARIO #1 — 5 parallel varied queries, no cross-leakage in traces."""

    QUERIES = [
        CANONICAL,
        "Need a CRM platform with email automation and lead scoring for our SaaS startup",
        "Looking for healthcare appointment scheduling software with HIPAA compliance",
        "We need an e-commerce checkout solution that supports subscriptions and trials",
        "Construction project management tool with Gantt charts and timesheet tracking",
    ]

    def test_5_concurrent_runs_no_cross_leakage(self):
        run_ids = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = [pool.submit(_post_match, q) for q in self.QUERIES]
            for f in as_completed(futs):
                r = f.result()
                assert r.status_code == 202
                run_ids.append(r.json()["run_id"])

        # Poll all in parallel
        with ThreadPoolExecutor(max_workers=5) as pool:
            docs = list(pool.map(lambda rid: _poll(rid, timeout_s=180), run_ids))

        for rid, doc in zip(run_ids, docs):
            assert doc["status"] == "completed", f"run {rid} status={doc.get('status')}"
            # The run doc's run_id must match what we requested
            assert doc.get("run_id") == rid
            tr = _trace(rid)
            # Trace run_id must match
            assert tr.get("run_id") == rid, f"trace run_id mismatch: {tr.get('run_id')} vs {rid}"
            # Top-3 must have >=3 entries
            assert len(doc.get("result") or []) >= 3


# ---------------------------------------------------------------------------
class TestWSOrderingNoCrossTalk:
    """SCENARIO #2 — WS events monotonic on ts; started precedes completed."""

    @pytest.mark.asyncio
    async def test_two_runs_isolated_and_ordered(self):
        # Fire two runs sequentially and connect WS to each
        async def run_and_collect(query: str):
            r = _post_match(query)
            assert r.status_code == 202
            run_id = r.json()["run_id"]
            url = f"{WS_BASE}/api/ws/match/{run_id}"
            events = []
            async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
                end = time.time() + 120
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    except asyncio.TimeoutError:
                        break
                    msg = json.loads(raw)
                    events.append(msg)
                    if msg.get("type") in ("run_completed", "run_failed"):
                        break
            return run_id, events

        rid_a, ev_a = await run_and_collect(CANONICAL)
        rid_b, ev_b = await run_and_collect(self_query := "Need a CRM platform for SaaS startup with lead scoring features")

        # Isolation: events on rid_a all carry rid_a, never rid_b, and vice versa
        for e in ev_a:
            if "run_id" in e:
                assert e["run_id"] == rid_a, f"cross-talk: {e}"
        for e in ev_b:
            if "run_id" in e:
                assert e["run_id"] == rid_b, f"cross-talk: {e}"

        # Ordering: ws_emitted_at monotonic non-decreasing
        for ev in (ev_a, ev_b):
            ts_list = [e.get("ws_emitted_at") or e.get("ts") for e in ev if (e.get("ws_emitted_at") or e.get("ts"))]
            for i in range(1, len(ts_list)):
                assert ts_list[i] >= ts_list[i - 1], f"non-monotonic ts: {ts_list[i-1]} -> {ts_list[i]}"

        # For each agent, started ws_emitted_at < completed ws_emitted_at
        for ev in (ev_a, ev_b):
            started = {}
            for e in ev:
                if e.get("type") == "agent_step" and e.get("status") == "started":
                    started[e.get("agent")] = e.get("ws_emitted_at") or e.get("ts")
            for e in ev:
                if e.get("type") == "agent_step" and e.get("status") == "completed":
                    agent = e.get("agent")
                    end_ts = e.get("ws_emitted_at") or e.get("ts")
                    if agent in started and end_ts and started[agent]:
                        assert end_ts >= started[agent], f"{agent}: completed before started"


# ---------------------------------------------------------------------------
class TestTextileFlowConsistency5:
    """SCENARIO #5 — 5 sequential canonical runs; TextileFlow in top 3 every time."""

    def test_textileflow_top3_5_runs(self):
        all_top3_sets = []
        for i in range(5):
            r = _post_match(CANONICAL)
            assert r.status_code == 202
            doc = _poll(r.json()["run_id"], timeout_s=180)
            assert doc["status"] == "completed"
            result = doc["result"]
            top3 = result[:3]
            tf_present = any(
                (it.get("solutionId") == TEXTILE_ID) or ("textileflow" in (it.get("explanation") or "").lower())
                for it in top3
            )
            assert tf_present, f"run {i}: TextileFlow not in top3: {[it.get('solutionId') for it in top3]}"
            sol_ids = frozenset(it.get("solutionId") for it in top3)
            all_top3_sets.append(sol_ids)

        # Overlap >=2/3 across all pairs
        for i in range(len(all_top3_sets)):
            for j in range(i + 1, len(all_top3_sets)):
                overlap = len(all_top3_sets[i] & all_top3_sets[j])
                assert overlap >= 2, f"runs {i}&{j} overlap={overlap}: {all_top3_sets[i]} vs {all_top3_sets[j]}"


# ---------------------------------------------------------------------------
class TestRankingDeterminism:
    """SCENARIO #8 — top-5 identical across 2 sequential canonical runs."""

    def test_top5_deterministic(self):
        def run_once():
            r = _post_match(CANONICAL)
            doc = _poll(r.json()["run_id"], timeout_s=180)
            assert doc["status"] == "completed"
            return [it.get("solutionId") for it in doc["result"][:5]]

        a = run_once()
        b = run_once()
        # As a deterministic-ranking check, top-5 SETs must match (order can vary if tied)
        assert set(a) == set(b), f"top-5 sets differ: {a} vs {b}"


# ---------------------------------------------------------------------------
class TestTraceIntegrity:
    """SCENARIO #6 — WS unique (agent,status) order mirrors trace.steps order."""

    @pytest.mark.asyncio
    async def test_ws_order_matches_trace_order(self):
        r = _post_match(CANONICAL)
        run_id = r.json()["run_id"]
        url = f"{WS_BASE}/api/ws/match/{run_id}"
        events = []
        async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
            end = time.time() + 180
            while time.time() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                events.append(msg)
                if msg.get("type") in ("run_completed", "run_failed"):
                    break
        ws_pairs = []
        seen = set()
        for e in events:
            if e.get("type") == "agent_step":
                key = (e.get("agent"), e.get("status"))
                if key not in seen:
                    seen.add(key)
                    ws_pairs.append(key)

        # Wait briefly then fetch trace
        await asyncio.sleep(0.5)
        tr = _trace(run_id)
        steps = tr.get("steps", [])
        trace_pairs = []
        seen2 = set()
        for s in steps:
            key = (s.get("agent"), s.get("status"))
            if key not in seen2:
                seen2.add(key)
                trace_pairs.append(key)
        assert ws_pairs == trace_pairs, f"WS pairs != trace pairs\nWS:    {ws_pairs}\nTRACE: {trace_pairs}"

        # started_at monotonic non-decreasing on trace.steps
        starts = [s.get("started_at") for s in steps if s.get("started_at")]
        for i in range(1, len(starts)):
            assert starts[i] >= starts[i - 1], f"non-monotonic started_at: {starts[i-1]} -> {starts[i]}"


# ---------------------------------------------------------------------------
class TestContextCompressionKeywords:
    """SCENARIO #7 — 6000+ char payload preserves multi-tenant/GDPR/audit-log."""

    def test_keywords_preserved_after_compression(self):
        keywords = ["multi-tenant", "GDPR", "audit-log"]
        filler = "We are evaluating enterprise SaaS platforms across global business units. " * 200
        # Embed keywords across the payload
        text = (
            f"Our platform must be {keywords[0]} from day one. "
            + filler[:2200]
            + f" Compliance: full {keywords[1]} adherence including data subject access requests. "
            + filler[:2200]
            + f" Operations require an {keywords[2]} for every administrative mutation. "
            + filler[:1800]
        )
        assert len(text) >= 6000, f"text len={len(text)}"
        r = _post_match(text[:8000])
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        doc = _poll(run_id, timeout_s=240)
        assert doc["status"] == "completed", f"failed: {doc}"
        tr = _trace(run_id)
        steps = tr.get("steps", [])

        # ContextCompression completed step with compressed flag
        cc = [s for s in steps if _matches_agent(s.get("agent"), "ContextCompression") and s.get("status") == "completed"]
        assert cc, "ContextCompression completed step missing"
        compressed_flag = False
        token_estimate = None
        for s in cc:
            payload = s.get("payload") or {}
            if isinstance(payload, dict):
                if payload.get("compressed") is True:
                    compressed_flag = True
                token_estimate = payload.get("compression_token_estimate")
        # COMPRESS_TOKEN_THRESHOLD is tuned (compression.py L15) so that a
        # full-spec ~6000+ char requirement (such as the SCENARIO #7 input)
        # reliably engages the compression path. The user's hard gate
        # requires compression to be visibly active in the trace.
        print(f"\nContextCompression: compressed={compressed_flag} token_estimate={token_estimate}")
        assert token_estimate is not None and token_estimate > 0, "compression_token_estimate missing"
        assert compressed_flag is True, (
            f"compressed=True branch did NOT engage for a {len(text[:8000])}-char "
            f"requirement (token_estimate={token_estimate}). The COMPRESS_TOKEN_THRESHOLD "
            f"is too high relative to realistic input sizes."
        )

        # Parser persisted requirements include >=2 of keywords
        parser_steps = [s for s in steps if _matches_agent(s.get("agent"), "Parser") and s.get("status") == "completed"]
        assert parser_steps, "Parser completed step missing"
        blob_text = json.dumps(parser_steps).lower()
        kw_hits = sum(1 for k in keywords if k.lower() in blob_text)
        assert kw_hits >= 2, f"only {kw_hits} keywords preserved in parser step: {[k for k in keywords if k.lower() in blob_text]}"


# ---------------------------------------------------------------------------
class TestLatencyP95:
    """SCENARIO #11 — p95 RankingAgent rerank_latency_ms < 30000 across 10 runs."""

    def test_p95_under_30s(self):
        lats = []
        for i in range(10):
            r = _post_match(CANONICAL)
            doc = _poll(r.json()["run_id"], timeout_s=180)
            assert doc["status"] == "completed"
            tr = _trace(doc["run_id"])
            rk = [s for s in tr.get("steps", []) if _matches_agent(s.get("agent"), "Ranking") and s.get("status") == "completed"]
            assert rk, f"run {i}: no Ranking completed step"
            payload = rk[-1].get("payload") or {}
            lat = payload.get("rerank_latency_ms") or rk[-1].get("execution_ms")
            assert lat is not None, f"no rerank_latency_ms / execution_ms on Ranking step: {rk[-1]}"
            lats.append(float(lat))

        lats_sorted = sorted(lats)
        p95 = lats_sorted[int(0.95 * len(lats_sorted)) - 1] if len(lats_sorted) >= 2 else lats_sorted[-1]
        print(f"\nRanking latency distribution (ms): {lats}\np95={p95}")
        assert p95 < 30000, f"p95 latency {p95}ms exceeds 30000ms"


# ---------------------------------------------------------------------------
class TestWSChannelCleanup:
    """SCENARIO #10 — total_channels returns to baseline after sockets close."""

    @pytest.mark.asyncio
    async def test_ws_channel_cleanup_after_disconnect(self):
        def debug():
            return requests.get(f"{BASE_URL}/api/admin/orchestration/_debug", timeout=10).json()

        baseline = debug()["ws"]["total_channels"]

        # 5 sequential runs, each with 4 subscribers
        for _i in range(5):
            r = _post_match(CANONICAL)
            run_id = r.json()["run_id"]
            url = f"{WS_BASE}/api/ws/match/{run_id}"

            async def subscribe(ws_url=url):
                async with websockets.connect(ws_url, open_timeout=10, ping_interval=None) as ws:
                    end = time.time() + 180
                    while time.time() < end:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        except asyncio.TimeoutError:
                            return
                        msg = json.loads(raw)
                        if msg.get("type") in ("run_completed", "run_failed", "run_already_finished"):
                            return

            await asyncio.gather(*[subscribe() for _ in range(4)])

        # Give cleanup a moment
        await asyncio.sleep(2.0)
        after = debug()["ws"]["total_channels"]
        assert after <= baseline, f"channel leak: baseline={baseline}, after={after}"
