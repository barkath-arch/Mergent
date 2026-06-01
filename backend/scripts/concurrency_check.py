"""Concurrency + WS integrity test.

Sends 5 distinct /api/match requests in parallel, each with its own WS
subscriber, and asserts:
  1. All 5 runs complete successfully.
  2. Each WS subscriber receives events ONLY for its own run_id (no cross-talk).
  3. Each WS subscriber sees ≥5 step events (the spec's minimum).

Run:
    cd /app/backend
    python -m scripts.concurrency_check
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import httpx
import websockets

BACKEND_HTTP = os.environ.get("APP_URL") or "http://localhost:8001"
BACKEND_WS = BACKEND_HTTP.replace("http://", "ws://").replace("https://", "wss://")

QUERIES = [
    "Inventory management for textile business with vendor portal",
    "We need a modern CRM with sales pipeline and lead scoring for our B2B SaaS",
    "HR system with payroll and onboarding for a 200 person company",
    "Headless e-commerce platform with multi-vendor marketplace",
    "Project management tool with gantt charts and time tracking",
]


async def _listen_ws(run_id: str, collected: List[Dict[str, Any]]) -> None:
    url = f"{BACKEND_WS}/api/ws/match/{run_id}"
    try:
        async with websockets.connect(url, ping_interval=20) as ws:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=90)
                except asyncio.TimeoutError:
                    return
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue
                collected.append(evt)
                if evt.get("type") in ("run_completed", "run_failed", "run_already_finished"):
                    return
    except Exception as exc:
        print(f"[ws {run_id[:8]}] error: {exc}")


async def _kick_run(client: httpx.AsyncClient, idx: int, query: str) -> Dict[str, Any]:
    r = await client.post(f"{BACKEND_HTTP}/api/match", json={"requirement_text": query})
    r.raise_for_status()
    return {"idx": idx, "query": query, "run_id": r.json()["run_id"]}


async def _wait_for_completion(client: httpx.AsyncClient, run_id: str, timeout_s: int = 120) -> Dict[str, Any]:
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = await client.get(f"{BACKEND_HTTP}/api/match/{run_id}")
        r.raise_for_status()
        doc = r.json()
        if doc["status"] in ("completed", "failed"):
            return doc
        await asyncio.sleep(0.5)
    raise TimeoutError(f"timeout for {run_id}")


async def main() -> int:
    async with httpx.AsyncClient(timeout=15) as client:
        kicks = await asyncio.gather(*[_kick_run(client, i, q) for i, q in enumerate(QUERIES)])
    run_ids = [k["run_id"] for k in kicks]
    print(f"[concurrency] kicked {len(run_ids)} runs: {[r[:8] for r in run_ids]}")

    # Start WS listeners for each run in parallel
    collected: Dict[str, List[Dict[str, Any]]] = {rid: [] for rid in run_ids}
    listeners = [asyncio.create_task(_listen_ws(rid, collected[rid])) for rid in run_ids]

    # Wait for all runs to complete via REST polling, with a generous timeout.
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*[_wait_for_completion(client, rid) for rid in run_ids])

    # Wait for listeners to drain (run_completed events).
    try:
        await asyncio.wait_for(asyncio.gather(*listeners, return_exceptions=True), timeout=10)
    except asyncio.TimeoutError:
        pass

    # Verification
    ok = True
    for k, doc in zip(kicks, results):
        rid = k["run_id"]
        events = collected[rid]
        if doc["status"] != "completed":
            print(f"[concurrency] FAIL run {rid[:8]}: status={doc['status']}")
            ok = False
            continue
        # Cross-talk check: every event with run_id MUST match.
        cross = [e for e in events if e.get("run_id") and e["run_id"] != rid]
        if cross:
            print(f"[concurrency] FAIL run {rid[:8]}: received {len(cross)} cross-talk events")
            ok = False
            continue
        step_events = [e for e in events if e.get("type") == "agent_step"]
        if len(step_events) < 5:
            print(f"[concurrency] FAIL run {rid[:8]}: only {len(step_events)} agent_step events")
            ok = False
            continue
        agents_seen = sorted({e.get("agent") for e in step_events if e.get("agent")})
        print(f"[concurrency] OK run {rid[:8]}: {len(events)} events, agents={agents_seen}")

    if ok:
        print("\n[concurrency] OVERALL: PASS")
        return 0
    print("\n[concurrency] OVERALL: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
