"""MERGENT Phase 0 — FastAPI entrypoint.

Routes (all under /api):
  POST   /api/match
  GET    /api/match/{run_id}
  GET    /api/match/{run_id}/trace
  WS     /api/ws/match/{run_id}
  POST   /api/admin/solutions/reindex
  GET    /api/admin/providers/health
  GET    /api/admin/orchestration/runs
  GET    /api/health
  GET    /api/openapi.json  (FastAPI built-in)

Concurrency: each POST /api/match creates an asyncio task to run the pipeline.
Up to N concurrent runs share the FastAPI event loop without contention because
each run owns its own `ctx` and its own per-run WSManager channel. See
services/orchestrator.py for the documented concurrency model.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from db import close_db, ensure_indexes, get_db, with_retry  # noqa: E402
from models import MatchAcceptedResponse, MatchRequest  # noqa: E402
from services.ai_provider import get_ai_provider  # noqa: E402
from services.logging_config import get_logger, setup_logging  # noqa: E402
from services.orchestrator import get_orchestrator  # noqa: E402
from services.vector_index import get_vector_index  # noqa: E402
from services.ws_manager import get_ws_manager  # noqa: E402

setup_logging()
logger = get_logger(__name__)


app = FastAPI(
    title="MERGENT — AI-Orchestrated Software Acquisition",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
api_router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    db = get_db()
    try:
        await ensure_indexes()
    except Exception as exc:
        logger.warning("startup_index_setup_failed", extra={"error": str(exc)})
    # Warm provider singleton (loads env, builds chain).
    try:
        get_ai_provider()
    except Exception as exc:
        logger.error("ai_provider_init_failed", extra={"error": str(exc)})
    # Load embeddings into the vector index from Mongo.
    try:
        vec = get_vector_index()
        items: List[tuple] = []
        async for d in db.solutions.find({"embedding": {"$exists": True, "$ne": []}}, {"_id": 1, "embedding": 1}):
            items.append((d["_id"], d["embedding"]))
        await vec.rebuild(items)
        logger.info("vector_index_loaded_on_startup", extra={"size": len(items)})
    except Exception as exc:
        logger.warning("vector_index_load_failed", extra={"error": str(exc)})


@app.on_event("shutdown")
async def _shutdown() -> None:
    close_db()


# ---------------------------------------------------------------------------
# /api/match endpoints
# ---------------------------------------------------------------------------
def _validate_requirement_text(text: Optional[str]) -> str:
    if not isinstance(text, str):
        raise HTTPException(status_code=422, detail={"error": "invalid_type"})
    stripped = text.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail={"error": "empty_requirement"})
    if len(stripped) < 5:
        raise HTTPException(status_code=400, detail={"error": "requirement_too_short", "min_chars": 5})
    if len(stripped) > 8000:
        raise HTTPException(status_code=400, detail={"error": "requirement_too_long", "max_chars": 8000})
    return stripped


@api_router.post("/match", response_model=MatchAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_match(payload: MatchRequest) -> MatchAcceptedResponse:
    text = _validate_requirement_text(payload.requirement_text)
    db = get_db()
    run_id = _new_uuid()
    now = _now_iso()
    run_doc = {
        "_id": run_id,
        "requirement_text": text,
        "status": "running",
        "steps": [],
        "result": None,
        "total_execution_ms": 0,
        "total_tokens": 0,
        "providers_used": [],
        "fallback_count": 0,
        "retry_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await with_retry(lambda: db.orchestration_runs.insert_one(run_doc))

    orch = get_orchestrator()
    asyncio.create_task(orch.run_match(text, run_id))
    return MatchAcceptedResponse(run_id=run_id)


@api_router.get("/match/{run_id}")
async def get_match(run_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db.orchestration_runs.find_one({"_id": run_id})
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "run_not_found"})
    return _serialize_run(doc)


@api_router.get("/match/{run_id}/trace")
async def get_match_trace(run_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db.orchestration_runs.find_one({"_id": run_id})
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "run_not_found"})
    return {
        "run_id": run_id,
        "status": doc.get("status"),
        "total_execution_ms": doc.get("total_execution_ms", 0),
        "total_tokens": doc.get("total_tokens", 0),
        "providers_used": doc.get("providers_used", []),
        "fallback_count": doc.get("fallback_count", 0),
        "retry_count": doc.get("retry_count", 0),
        "steps": doc.get("steps", []),
    }


@app.websocket("/api/ws/match/{run_id}")
async def ws_match(websocket: WebSocket, run_id: str) -> None:
    ws_manager = get_ws_manager()
    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            # We don't expect inbound messages but keep the connection open.
            msg = await websocket.receive_text()
            if msg.strip().lower() == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws_loop_error", extra={"error": str(exc), "run_id": run_id})
    finally:
        await ws_manager.disconnect(run_id, websocket)
        await ws_manager.cleanup(run_id)


# ---------------------------------------------------------------------------
# Admin / health endpoints
# ---------------------------------------------------------------------------
@api_router.post("/admin/solutions/reindex")
async def admin_reindex() -> Dict[str, Any]:
    # TODO(Phase 1): protect this endpoint with auth.
    try:
        from tasks import reindex_all_solutions
        async_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: reindex_all_solutions.apply_async(queue="mergent"),
            ),
            timeout=2.0,
        )
        return {"queued": True, "task_id": async_result.id}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail={"error": "queue_unavailable", "retry_after_s": 5})
    except Exception as exc:
        logger.error("reindex_enqueue_failed", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail={"error": "queue_unavailable", "retry_after_s": 5})


@api_router.get("/admin/orchestration/_debug")
async def admin_orchestration_debug() -> Dict[str, Any]:
    """Introspection endpoint for tests — exposes WS channel counts and
    provider cache state so memory-leak / channel-cleanup assertions can be
    made externally. Phase 0: unauthenticated. TODO(Phase 1): protect.
    """
    ws = get_ws_manager()
    provider = get_ai_provider()
    return {
        "ws": ws.channel_counts(),
        "provider_chain": provider.provider_chain,
        "vector_index_size": get_vector_index().size,
        "ts": _now_iso(),
    }


@api_router.get("/admin/providers/health")
async def admin_providers_health() -> Dict[str, Any]:
    provider = get_ai_provider()
    return {"providers": provider.health_snapshot(), "chain": provider.provider_chain}


@api_router.get("/admin/orchestration/runs")
async def admin_runs(limit: int = 20) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    db = get_db()
    cursor = db.orchestration_runs.find(
        {},
        {
            "_id": 1,
            "requirement_text": 1,
            "status": 1,
            "total_execution_ms": 1,
            "total_tokens": 1,
            "fallback_count": 1,
            "providers_used": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(limit)
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        items.append(
            {
                "run_id": d["_id"],
                "requirement_excerpt": (d.get("requirement_text") or "")[:120],
                "status": d.get("status"),
                "total_execution_ms": d.get("total_execution_ms", 0),
                "total_tokens": d.get("total_tokens", 0),
                "fallback_count": d.get("fallback_count", 0),
                "providers_used": d.get("providers_used", []),
                "created_at": d.get("created_at"),
            }
        )
    return {"runs": items}


@api_router.get("/health")
async def health() -> Dict[str, Any]:
    db = get_db()
    mongo_status = "down"
    try:
        await asyncio.wait_for(db.command("ping"), timeout=2.0)
        mongo_status = "up"
    except Exception:
        mongo_status = "down"

    redis_status = "down"
    try:
        import redis as redis_sync
        r = redis_sync.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            socket_timeout=1, socket_connect_timeout=1,
        )
        if r.ping():
            redis_status = "up"
    except Exception:
        redis_status = "down"

    celery_status = "unknown"
    try:
        from celery_app import celery_app
        insp = celery_app.control.inspect(timeout=1)
        active = insp.ping() if insp else None
        celery_status = "up" if active else "down"
    except Exception:
        celery_status = "down"

    provider = get_ai_provider()
    return {
        "status": "ok" if mongo_status == "up" else "degraded",
        "mongo": mongo_status,
        "redis": redis_status,
        "celery": celery_status,
        "providers": provider.health_snapshot(),
        "vector_index_size": get_vector_index().size,
        "ts": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def _serialize_run(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": doc["_id"],
        "requirement_text": doc.get("requirement_text", ""),
        "status": doc.get("status"),
        "steps": doc.get("steps", []),
        "result": doc.get("result"),
        "total_execution_ms": doc.get("total_execution_ms", 0),
        "total_tokens": doc.get("total_tokens", 0),
        "providers_used": doc.get("providers_used", []),
        "fallback_count": doc.get("fallback_count", 0),
        "retry_count": doc.get("retry_count", 0),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
