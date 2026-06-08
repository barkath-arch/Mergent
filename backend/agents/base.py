"""BaseAgent — Phase AGENTS Step 1 foundation.

Provides a class hierarchy for the 6 existing pipeline agents (IntakeAgent,
RequirementParserAgent, EmbeddingAgent, SemanticSearchAgent,
ContextCompressionAgent, RankingAgent) without breaking the working pipeline.

Each subclass:
  - declares `agent_name` and `agent_version`
  - implements `async def run(self, input: dict) -> dict`

Callers (the orchestrator) invoke `await agent.execute(input, run_id=...)`
which wraps `run()` with timing, success/failure logging, and persistence to
`db.agent_runs`. AI provider calls made via `self._llm()` / `self._embed()`
flow `agent_name` into `db.ai_usage_logs` automatically.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from db import get_db
from services.ai_provider import (
    AIProviderService,
    ChatResult,
    EmbedResult,
    get_ai_provider,
)
from services.logging_config import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseAgent:
    """Abstract base for all Mergent agents."""

    agent_name: str = "BaseAgent"
    agent_version: str = "1.0.0"

    def __init__(self, provider: Optional[AIProviderService] = None) -> None:
        self.provider: AIProviderService = provider or get_ai_provider()

    # ------------------------------------------------------------------ #
    # Subclasses override this.
    # ------------------------------------------------------------------ #
    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Wrappers around AIProviderService that pass agent_name automatically.
    # ------------------------------------------------------------------ #
    async def _llm(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        json_mode: bool = True,
        max_tokens: int = 1500,
    ) -> Tuple[Any, ChatResult]:
        """Run an LLM call; logs to `ai_usage_logs` with `self.agent_name`.

        Returns:
            `(parsed_dict, ChatResult)` if `json_mode=True`
            `(text, ChatResult)` if `json_mode=False`
        """
        msgs = list(messages)
        if system_prompt:
            msgs = [{"role": "system", "content": system_prompt}] + msgs

        if json_mode:
            parsed, result = await self.provider.chat_json(
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_name=self.agent_name,
            )
            return parsed, result
        result = await self.provider.chat(
            messages=msgs,
            json_mode=False,
            temperature=temperature,
            max_tokens=max_tokens,
            agent_name=self.agent_name,
        )
        return result.text, result

    async def _embed(self, text: str) -> Tuple[List[float], EmbedResult]:
        """Run an embedding call; logs to `ai_usage_logs` with `self.agent_name`."""
        result = await self.provider.embed([text], agent_name=self.agent_name)
        vec = result.vectors[0] if result.vectors else []
        return vec, result

    # ------------------------------------------------------------------ #
    # Per-execution wrapper: times, logs to agent_runs, re-raises on error.
    # ------------------------------------------------------------------ #
    async def execute(
        self,
        input: Dict[str, Any],  # noqa: A002
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        started_at = _now_iso()
        output: Dict[str, Any] = {}
        success = True
        error_msg: Optional[str] = None
        try:
            output = await self.run(input)
            return output
        except Exception as exc:  # noqa: BLE001
            success = False
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "agent_execute_failed",
                extra={"agent": self.agent_name, "run_id": run_id, "error": error_msg},
            )
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            # Fire-and-forget log; don't fail the pipeline if Mongo hiccups.
            try:
                await self._log_run(
                    input_payload=_sanitize(input),
                    output_payload=_sanitize(output),
                    duration_ms=duration_ms,
                    success=success,
                    error=error_msg,
                    run_id=run_id,
                    started_at=started_at,
                )
            except Exception as log_exc:  # noqa: BLE001
                logger.warning(
                    "agent_run_log_failed",
                    extra={"agent": self.agent_name, "error": str(log_exc)},
                )

    async def _log_run(
        self,
        input_payload: Dict[str, Any],
        output_payload: Dict[str, Any],
        duration_ms: int,
        success: bool,
        error: Optional[str] = None,
        run_id: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        db = get_db()
        doc = {
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "run_id": run_id,
            "input_json": input_payload,
            "output_json": output_payload,
            "duration_ms": duration_ms,
            "success": success,
            "error": error,
            "started_at": started_at,
            "created_at": datetime.now(timezone.utc),
        }
        await db.agent_runs.insert_one(doc)


# Keys that may carry large/private payloads we don't persist verbatim.
_LARGE_KEYS = {
    "query_vector",
    "embedding",
    "candidates",          # full solution docs
    "_chat_result",
    "_embed_result",
    "candidates_meta",
}
_PREVIEW_KEYS = {
    "normalized_text",
    "requirement_text",
    "requirement_summary",
    "keyword_query",
}


def _sanitize(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"_raw_type": type(payload).__name__}
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if k in _LARGE_KEYS:
            if isinstance(v, list):
                out[k + "_len"] = len(v)
            else:
                out[k + "_present"] = True
            continue
        if k in _PREVIEW_KEYS and isinstance(v, str):
            out[k] = v[:300]
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            if v and isinstance(v[0], (str, int, float, bool)):
                out[k] = v[:20]
            else:
                out[k + "_len"] = len(v)
        elif isinstance(v, dict):
            shallow = {
                ik: iv for ik, iv in v.items()
                if isinstance(iv, (str, int, float, bool)) or iv is None
            }
            out[k] = shallow if shallow else {"_keys": list(v.keys())[:20]}
        else:
            out[k] = str(v)[:200]
    return out
