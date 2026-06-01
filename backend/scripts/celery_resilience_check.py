"""Celery resilience check.

Verifies that killing the Celery worker mid-flight and restarting it doesn't
lose embedding jobs. Strategy:
  1. Force-reembed all 10 solutions by clearing their `embedding` field.
  2. Trigger the reindex flow (enqueues 10 embed tasks via Redis SETNX lock).
  3. Immediately kill the worker via supervisorctl.
  4. Wait a moment then restart the worker.
  5. Confirm all 10 solutions end up with embeddings.

Run:
    cd /app/backend
    python -m scripts.celery_resilience_check
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = client[os.environ["DB_NAME"]]

    print("[celery-resilience] clearing embeddings + locks")
    await db.solutions.update_many({}, {"$set": {"embedding": [], "embedding_updated_at": None}})

    # Clear any leftover Redis locks so try_enqueue_embed succeeds.
    import redis as redis_sync
    r = redis_sync.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    for k in r.keys("embed:lock:*"):
        r.delete(k)

    ids = [d["_id"] async for d in db.solutions.find({}, {"_id": 1})]
    print(f"[celery-resilience] {len(ids)} solutions to re-embed")

    from tasks import try_enqueue_embed
    for sid in ids:
        res = try_enqueue_embed(sid)
        if not res.get("queued"):
            print(f"[celery-resilience] enqueue failed for {sid}: {res}")

    # Wait a moment, then kill the worker mid-flight.
    await asyncio.sleep(0.4)
    print("[celery-resilience] STOPPING celery_worker mid-flight ...")
    subprocess.run(["sudo", "supervisorctl", "stop", "celery_worker"], check=False)

    await asyncio.sleep(2)
    print("[celery-resilience] STARTING celery_worker ...")
    subprocess.run(["sudo", "supervisorctl", "start", "celery_worker"], check=False)

    # Wait for embeddings to materialize.
    deadline = time.time() + 120
    final = 0
    while time.time() < deadline:
        final = await db.solutions.count_documents({"embedding": {"$ne": []}})
        print(f"[celery-resilience] embedded {final}/{len(ids)} ...")
        if final >= len(ids):
            break
        await asyncio.sleep(3)

    client.close()
    if final >= len(ids):
        print("[celery-resilience] OVERALL: PASS")
        return 0
    print("[celery-resilience] OVERALL: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
