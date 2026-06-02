"""Celery tasks for embedding and reindexing solutions.

The tasks use a synchronous bridge to call the async AIProviderService and motor.
We use `asyncio.run()` per task — each task runs in its own short-lived loop.

Duplicate-prevention:
  - Before enqueue, the caller acquires a Redis SETNX lock `embed:lock:{solution_id}`
    with 5-min TTL.
  - At task start, we re-check the lock and the solution's `embedding_updated_at`
    timestamp against the enqueue ts to short-circuit stale work.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis as redis_sync
from celery import shared_task
from motor.motor_asyncio import AsyncIOMotorClient

from celery_app import celery_app  # noqa: F401  (registers app)
from services.logging_config import get_logger

logger = get_logger(__name__)


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EMBED_LOCK_TTL_S = 300


def _redis() -> redis_sync.Redis:
    return redis_sync.Redis.from_url(REDIS_URL, socket_timeout=2, socket_connect_timeout=2)


def _run_async(coro):
    """Run an async coroutine from within a Celery sync task."""
    return asyncio.run(coro)


async def _async_embed_solution(solution_id: str, enqueued_ts: float) -> Dict[str, Any]:
    from services.ai_provider import get_ai_provider
    from services.vector_index import get_vector_index

    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = client[os.environ["DB_NAME"]]
    try:
        doc = await db.solutions.find_one({"_id": solution_id})
        if not doc:
            return {"status": "missing", "solution_id": solution_id}

        # Skip if a fresher embedding already exists since enqueue.
        last_updated = doc.get("embedding_updated_at")
        if last_updated:
            try:
                last_ts = datetime.fromisoformat(last_updated).timestamp()
                if last_ts >= enqueued_ts:
                    logger.info(
                        "duplicate_embedding_skipped",
                        extra={"solution_id": solution_id, "reason": "fresher_embedding_exists"},
                    )
                    return {"status": "skipped", "solution_id": solution_id}
            except Exception:
                pass

        text_to_embed = _solution_to_embedding_text(doc)
        provider = get_ai_provider()
        result = await provider.embed([text_to_embed])
        vector = result.vectors[0] if result.vectors else []

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.solutions.update_one(
            {"_id": solution_id},
            {"$set": {"embedding": vector, "embedding_updated_at": now_iso, "updated_at": now_iso}},
        )

        index = get_vector_index()
        await index.upsert(solution_id, vector)
        logger.info(
            "solution_embedded",
            extra={"solution_id": solution_id, "dim": len(vector), "provider": result.provider_used},
        )
        return {"status": "ok", "solution_id": solution_id, "dim": len(vector)}
    finally:
        client.close()


def _solution_to_embedding_text(doc: Dict[str, Any]) -> str:
    parts = [
        doc.get("title", ""),
        doc.get("tagline", ""),
        f"Category: {doc.get('category', '')}",
        f"Tech stack: {', '.join(doc.get('tech_stack', []))}",
        f"Tags: {', '.join(doc.get('tags', []))}",
        doc.get("description", ""),
    ]
    return "\n".join(p for p in parts if p)


@shared_task(name="tasks.embed_solution", bind=True, max_retries=3, default_retry_delay=5)
def embed_solution(self, solution_id: str, enqueued_ts: Optional[float] = None) -> Dict[str, Any]:
    enqueued_ts = enqueued_ts if enqueued_ts is not None else time.time()

    # De-dupe lock re-check at task start.
    try:
        r = _redis()
        lock_key = f"embed:lock:{solution_id}"
        # If the lock is not present, someone may have already finished this work.
        # We still proceed but log.
        if not r.exists(lock_key):
            logger.info("embed_lock_missing_at_start", extra={"solution_id": solution_id})
    except Exception as exc:
        logger.warning("redis_lock_check_failed", extra={"error": str(exc)})

    try:
        result = _run_async(_async_embed_solution(solution_id, enqueued_ts))
        return result
    except Exception as exc:
        logger.exception("embed_solution_failed", extra={"solution_id": solution_id, "error": str(exc)})
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "solution_id": solution_id, "error": str(exc)}
    finally:
        # Release lock so future re-embeds are allowed.
        try:
            r = _redis()
            r.delete(f"embed:lock:{solution_id}")
        except Exception:
            pass


async def _async_reindex_all() -> Dict[str, Any]:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = client[os.environ["DB_NAME"]]
    ids: List[str] = []
    try:
        ids = [d["_id"] async for d in db.solutions.find({}, {"_id": 1})]
    finally:
        client.close()

    enqueued: List[str] = []
    skipped: List[str] = []
    try:
        r = _redis()
        for sid in ids:
            lock_key = f"embed:lock:{sid}"
            if r.set(lock_key, "1", nx=True, ex=EMBED_LOCK_TTL_S):
                embed_solution.apply_async(args=[sid, time.time()], queue="mergent")
                enqueued.append(sid)
            else:
                skipped.append(sid)
    except Exception as exc:
        logger.warning("reindex_enqueue_failed", extra={"error": str(exc)})
    return {"enqueued": enqueued, "skipped": skipped, "total": len(ids)}


@shared_task(name="tasks.reindex_all_solutions")
def reindex_all_solutions() -> Dict[str, Any]:
    return _run_async(_async_reindex_all())


# ---------------------------------------------------------------------------
# Phase 6 — Trust & Quality Agent sweep
# ---------------------------------------------------------------------------
@shared_task(name="tasks.recompute_trust_all")
def recompute_trust_all() -> Dict[str, Any]:
    """Nightly sweep — recomputes trust_score for every builder.
    Triggered by celery beat (see celery_app.beat_schedule)."""
    from services.trust_agent import recompute_all

    return _run_async(recompute_all())


def try_enqueue_embed(solution_id: str) -> Dict[str, Any]:
    """Acquire Redis NX lock and enqueue embed_solution. Returns status dict.

    Uses a 2-second Redis socket timeout so the caller (FastAPI request handler)
    fails fast when Redis is unavailable.
    """
    try:
        r = _redis()
        lock_key = f"embed:lock:{solution_id}"
        acquired = r.set(lock_key, "1", nx=True, ex=EMBED_LOCK_TTL_S)
        if not acquired:
            return {"queued": False, "reason": "duplicate_embedding_skipped"}
        embed_solution.apply_async(args=[solution_id, time.time()], queue="mergent")
        return {"queued": True}
    except Exception as exc:
        logger.warning("enqueue_embed_failed", extra={"error": str(exc), "solution_id": solution_id})
        return {"queued": False, "reason": "queue_unavailable", "error": str(exc)}
