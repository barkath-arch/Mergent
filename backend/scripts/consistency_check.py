"""Consistency check — runs the canonical textile query N times and asserts
TextileFlow ERP is in the top 3 every time.

Run:
    cd /app/backend
    python -m scripts.consistency_check
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import httpx

CANONICAL_QUERY = "Inventory management for textile business with vendor portal"
EXPECTED_TITLE = "TextileFlow ERP"
N_RUNS = 5
BACKEND_URL = os.environ.get("APP_URL") or "http://localhost:8001"


async def _wait_for_completion(client: httpx.AsyncClient, run_id: str, timeout_s: int = 120) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = await client.get(f"{BACKEND_URL}/api/match/{run_id}")
        r.raise_for_status()
        doc = r.json()
        if doc.get("status") in ("completed", "failed"):
            return doc
        await asyncio.sleep(1)
    raise TimeoutError(f"Run {run_id} did not complete within {timeout_s}s")


async def _resolve_title(client: httpx.AsyncClient, solution_id: str) -> str:
    # Quick lookup via Mongo (use motor directly here to avoid a public route).
    from motor.motor_asyncio import AsyncIOMotorClient
    mc = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = mc[os.environ["DB_NAME"]]
    try:
        doc = await db.solutions.find_one({"_id": solution_id}, {"title": 1})
        return doc["title"] if doc else "?"
    finally:
        mc.close()


async def main() -> int:
    print(f"[consistency] backend={BACKEND_URL}")
    print(f"[consistency] query={CANONICAL_QUERY!r}")
    print(f"[consistency] expecting top-3 to include {EXPECTED_TITLE!r}")

    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(1, N_RUNS + 1):
            r = await client.post(
                f"{BACKEND_URL}/api/match",
                json={"requirement_text": CANONICAL_QUERY},
            )
            r.raise_for_status()
            run_id = r.json()["run_id"]
            print(f"[consistency] run {i}/{N_RUNS} → {run_id}")

            doc = await _wait_for_completion(client, run_id)
            if doc.get("status") != "completed":
                print(f"[consistency] run {i} FAILED: {doc.get('error')}")
                results.append(False)
                continue

            ranked = doc.get("result") or []
            top3 = ranked[:3]
            top3_titles = [await _resolve_title(client, r["solutionId"]) for r in top3]
            present = EXPECTED_TITLE in top3_titles
            print(f"[consistency] run {i} top3: {top3_titles}  -> {'PASS' if present else 'FAIL'}")
            results.append(present)

    passed = sum(1 for x in results if x)
    total = len(results)
    print(f"\n[consistency] {passed}/{total} runs passed")
    if passed == total and total == N_RUNS:
        print("[consistency] OVERALL: PASS")
        return 0
    print("[consistency] OVERALL: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
