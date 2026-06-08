"""MergentOrchestrator — sequences agents and emits per-step WS events.

Phase AGENTS Step 1 changes:
  - Renamed Mongo collection from `orchestration_runs` to `match_runs`.
  - `run_match` now accepts an optional `buyer_id` (string) recorded on the doc.
  - Per agent, an additional human-readable `agent_step` event is emitted with
    `{event: "agent_step", type: "agent_step", agent, status: "running"|"done",
    message: "...", ts}`. The existing detailed events (`started`/`completed`/
    `failed`/`retried`, `provider_fallback`, `run_completed`/`run_failed`) are
    preserved — additive, not replacing.
  - Synthetic "Preparing your recommendations..." emitted just before
    `run_completed`.

Concurrency: unchanged — each `run_match(...)` is its own asyncio.Task with an
isolated `ctx` dict. Per-run WSManager channel keeps subscribers isolated.
"""
from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from db import get_db, with_retry
from services.ai_provider import ChatResult, EmbedResult
from services.logging_config import get_logger
from services.ws_manager import get_ws_manager

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


from agents import intake as _intake
from agents import parser as _parser
from agents import embedding as _embedding
from agents import search as _search
from agents import compression as _compression
from agents import ranking as _ranking


PIPELINE: List[Dict[str, Any]] = [
    {"agent": "IntakeAgent", "run": _intake.run},
    {"agent": "RequirementParserAgent", "run": _parser.run},
    {"agent": "EmbeddingAgent", "run": _embedding.run},
    {"agent": "SemanticSearchAgent", "run": _search.run},
    {"agent": "ContextCompressionAgent", "run": _compression.run},
    {"agent": "RankingAgent", "run": _ranking.run},
]

# Human-readable progress messages shown to the user during the run.
AGENT_PROGRESS_MESSAGES: Dict[str, str] = {
    "IntakeAgent": "Understanding your business requirement...",
    "RequirementParserAgent": "Understanding your business requirement...",
    "EmbeddingAgent": "Searching the marketplace semantically...",
    "SemanticSearchAgent": "Searching the marketplace semantically...",
    "ContextCompressionAgent": "Validating top results...",
    "RankingAgent": "Scoring solution matches...",
}
SYNTHETIC_FINAL_MESSAGE = "Preparing your recommendations..."


class MergentOrchestrator:
    async def run_match(
        self,
        requirement_text: str,
        run_id: str,
        buyer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ws = get_ws_manager()
        db = get_db()
        ctx: Dict[str, Any] = {
            "requirement_text": requirement_text,
            "run_id": run_id,
            "buyer_id": buyer_id,
        }
        total_t0 = time.perf_counter()
        providers_used: List[str] = []
        total_tokens = 0
        fallback_count = 0
        retry_count = 0

        try:
            for spec in PIPELINE:
                agent_name: str = spec["agent"]
                step_record = await self._run_agent(
                    agent_name=agent_name,
                    agent_fn=spec["run"],
                    ctx=ctx,
                    run_id=run_id,
                    ws=ws,
                    db=db,
                )
                if step_record.get("provider_used"):
                    providers_used.append(step_record["provider_used"])
                if step_record.get("token_usage"):
                    total_tokens += int(step_record["token_usage"].get("total", 0))
                if step_record.get("fallback_event"):
                    fallback_count += 1
                retry_count += int(step_record.get("retry_count") or 0)

                if step_record["status"] == "failed":
                    raise RuntimeError(f"{agent_name} failed: {step_record.get('error')}")

            ranked = ctx.get("ranked", [])
            total_ms = int((time.perf_counter() - total_t0) * 1000)

            # Synthetic final progress message before run_completed.
            await ws.broadcast(run_id, {
                "type": "agent_step",
                "event": "agent_step",
                "agent": "Orchestrator",
                "status": "running",
                "message": SYNTHETIC_FINAL_MESSAGE,
                "ts": _now_iso(),
            })

            await with_retry(lambda: db.match_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "completed",
                        "result": ranked,
                        "total_execution_ms": total_ms,
                        "total_tokens": total_tokens,
                        "providers_used": list(set(providers_used)),
                        "fallback_count": fallback_count,
                        "retry_count": retry_count,
                        "updated_at": _now_iso(),
                    }
                },
            ))
            await ws.mark_finished(run_id)
            await ws.broadcast(run_id, {
                "type": "run_completed",
                "run_id": run_id,
                "total_execution_ms": total_ms,
                "total_tokens": total_tokens,
                "result_count": len(ranked),
                "ts": _now_iso(),
            })
            logger.info(
                "run_completed",
                extra={
                    "run_id": run_id,
                    "buyer_id": buyer_id,
                    "total_execution_ms": total_ms,
                    "total_tokens": total_tokens,
                    "result_count": len(ranked),
                    "providers_used": list(set(providers_used)),
                },
            )
            return {"status": "completed", "result": ranked}
        except Exception as exc:
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            err = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc()
            err_doc = {"type": type(exc).__name__, "message": str(exc), "trace": tb[:2000]}
            await with_retry(lambda: db.match_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "failed",
                        "total_execution_ms": total_ms,
                        "total_tokens": total_tokens,
                        "providers_used": list(set(providers_used)),
                        "fallback_count": fallback_count,
                        "retry_count": retry_count,
                        "error": err_doc,
                        "updated_at": _now_iso(),
                    }
                },
            ))
            await ws.mark_finished(run_id)
            await ws.broadcast(run_id, {
                "type": "run_failed",
                "run_id": run_id,
                "error": err,
                "ts": _now_iso(),
            })
            logger.exception("run_failed", extra={"run_id": run_id, "error": err})
            return {"status": "failed", "error": err}

    async def _run_agent(
        self,
        agent_name: str,
        agent_fn: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        ctx: Dict[str, Any],
        run_id: str,
        ws,
        db,
    ) -> Dict[str, Any]:
        started_at = _now_iso()
        t0 = time.perf_counter()
        progress_msg = AGENT_PROGRESS_MESSAGES.get(agent_name, "")

        # Legacy detailed `started` event (existing consumers depend on this).
        started_event = {
            "type": "agent_step",
            "run_id": run_id,
            "agent": agent_name,
            "status": "started",
            "started_at": started_at,
            "ts": started_at,
        }
        await ws.broadcast(run_id, started_event)

        # NEW human-readable `running` event.
        if progress_msg:
            await ws.broadcast(run_id, {
                "type": "agent_step",
                "event": "agent_step",
                "agent": agent_name,
                "status": "running",
                "message": progress_msg,
                "ts": started_at,
            })

        await with_retry(lambda: db.match_runs.update_one(
            {"_id": run_id},
            {"$push": {"steps": {
                "agent": agent_name,
                "run_id": run_id,
                "status": "started",
                "started_at": started_at,
                "ws_emitted_at": started_at,
            }}, "$set": {"updated_at": _now_iso()}},
        ))

        try:
            output = await agent_fn(ctx)
        except Exception as exc:
            ended_at = _now_iso()
            execution_ms = int((time.perf_counter() - t0) * 1000)
            err_payload = {
                "type": type(exc).__name__,
                "message": str(exc),
                "retry_count": 0,
            }
            step = {
                "agent": agent_name,
                "run_id": run_id,
                "status": "failed",
                "started_at": started_at,
                "ended_at": ended_at,
                "execution_ms": execution_ms,
                "provider_used": None,
                "token_usage": None,
                "ws_emitted_at": ended_at,
                "error": err_payload,
            }
            failed_event = {**step, "type": "agent_step", "ts": ended_at}
            await ws.broadcast(run_id, failed_event)
            await with_retry(lambda: db.match_runs.update_one(
                {"_id": run_id},
                {"$push": {"steps": step}, "$set": {"updated_at": _now_iso()}},
            ))
            logger.exception("agent_failed", extra={"run_id": run_id, "agent": agent_name})
            return step

        provider_used: Optional[str] = None
        token_usage: Optional[Dict[str, int]] = None
        fallback_event = None
        retries = 0

        chat_result: Optional[ChatResult] = output.pop("_chat_result", None)
        embed_result: Optional[EmbedResult] = output.pop("_embed_result", None)
        if chat_result is not None:
            provider_used = chat_result.provider_used
            token_usage = chat_result.token_usage
            fallback_event = chat_result.fallback_event
            retries = chat_result.retry_count
        elif embed_result is not None:
            provider_used = embed_result.provider_used
            token_usage = embed_result.token_usage
            fallback_event = embed_result.fallback_event
            retries = embed_result.retry_count

        ctx.update(output)

        ended_at = _now_iso()
        execution_ms = int((time.perf_counter() - t0) * 1000)
        retrieval_latency_ms = None
        rerank_latency_ms = None
        if agent_name == "SemanticSearchAgent":
            retrieval_latency_ms = output.get("retrieval_latency_ms")
        if agent_name == "RankingAgent":
            rerank_latency_ms = execution_ms

        public_payload = _sanitize_payload(agent_name, output)

        step = {
            "agent": agent_name,
            "run_id": run_id,
            "status": "completed",
            "started_at": started_at,
            "ended_at": ended_at,
            "execution_ms": execution_ms,
            "provider_used": provider_used,
            "token_usage": token_usage,
            "retrieval_latency_ms": retrieval_latency_ms,
            "rerank_latency_ms": rerank_latency_ms,
            "fallback_event": fallback_event,
            "ws_emitted_at": ended_at,
            "error": None,
            "retry_count": retries,
            "payload": public_payload,
        }
        # Legacy detailed `completed` event.
        await ws.broadcast(run_id, {**step, "type": "agent_step", "ts": ended_at})
        # NEW human-readable `done` event.
        if progress_msg:
            await ws.broadcast(run_id, {
                "type": "agent_step",
                "event": "agent_step",
                "agent": agent_name,
                "status": "done",
                "message": progress_msg,
                "ts": ended_at,
            })
        if fallback_event:
            await ws.broadcast(run_id, {
                "type": "provider_fallback",
                "run_id": run_id,
                "agent": agent_name,
                "from_provider": fallback_event.get("from_provider"),
                "to_provider": fallback_event.get("to_provider"),
                "reason": fallback_event.get("reason"),
                "ts": ended_at,
            })
        if retries > 0:
            await ws.broadcast(run_id, {
                "type": "agent_step",
                "run_id": run_id,
                "agent": agent_name,
                "status": "retried",
                "retry_count": retries,
                "ts": ended_at,
            })

        await with_retry(lambda: db.match_runs.update_one(
            {"_id": run_id},
            {"$push": {"steps": step}, "$set": {"updated_at": _now_iso()}},
        ))
        return step


def _sanitize_payload(agent_name: str, output: Dict[str, Any]) -> Dict[str, Any]:
    if agent_name == "EmbeddingAgent":
        return {
            "requirement_summary": output.get("requirement_summary", ""),
            "vector_dim": len(output.get("query_vector", []) or []),
        }
    if agent_name == "SemanticSearchAgent":
        return {
            "candidate_ids": output.get("candidate_ids", []),
            "retrieval_methods": output.get("retrieval_methods", {}),
            "retrieval_latency_ms": output.get("retrieval_latency_ms", 0),
            "keyword_count": output.get("keyword_count", 0),
            "vector_count": output.get("vector_count", 0),
            "top_k_used": output.get("top_k_used", 0),
        }
    if agent_name == "ContextCompressionAgent":
        return {
            "compressed": output.get("compressed", False),
            "compression_token_estimate": output.get("compression_token_estimate", 0),
            "candidate_count": len(output.get("candidates", []) or []),
        }
    if agent_name == "RankingAgent":
        ranked = output.get("ranked", []) or []
        return {
            "ranked_count": len(ranked),
            "top_3": [
                {"solutionId": r["solutionId"], "score": r["score"], "confidence": r["confidence"]}
                for r in ranked[:3]
            ],
        }
    if agent_name == "RequirementParserAgent":
        return {"parsed_requirement": output.get("parsed_requirement", {})}
    if agent_name == "IntakeAgent":
        return {
            "normalized_text_preview": (output.get("normalized_text") or "")[:200],
            "signals": output.get("signals", {}),
        }
    return {}


_singleton: Optional[MergentOrchestrator] = None


def get_orchestrator() -> MergentOrchestrator:
    global _singleton
    if _singleton is None:
        _singleton = MergentOrchestrator()
    return _singleton
