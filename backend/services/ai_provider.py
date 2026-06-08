"""AIProviderService — single LLM/embedding abstraction for MERGENT.

All LLM and embedding calls in the codebase MUST go through this module so that
provider failover, retry, timeout, and token-usage accounting happens uniformly.

Under the hood we use litellm (the same library `emergentintegrations.llm.chat.LlmChat`
uses) and route requests through the Emergent integration proxy when the API key
is the Emergent universal key (`sk-emergent-...`). This gives us OpenAI / Anthropic
/ Gemini access with one credential.

Phase AGENTS Step 1 additions:
  - `groq` provider (opt-in via `AI_PROVIDER_CHAIN`; uses direct Groq API when
    `GROQ_API_KEY` is set, otherwise attempts via the Emergent proxy)
  - per-call write to `ai_usage_logs` Mongo collection (provider, model,
    `agent_name`, tokens in/out, latency, estimated cost, success/error)
  - `chat()` and `chat_json()` and `embed()` all accept an optional `agent_name`
    kwarg used solely for logging — no behavioural change.

Concurrency: this module is async-only. The class is stateless besides a few
caches (provider health, embedding cache) protected by `asyncio.Lock`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import litellm
from emergentintegrations.llm.utils import get_integration_proxy_url

from services.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider catalogue.
# ---------------------------------------------------------------------------
PROVIDER_DEFAULT_CHAT_MODEL: Dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
}

# OpenAI supports response_format={"type":"json_object"} natively.
_JSON_MODE_NATIVE = {"openai", "groq"}

# Rough $/1k tokens used by the cost estimator. Numbers come from each
# provider's public pricing as of 2026. Used only for observability; not billed.
COST_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "openai:gpt-4o-mini":                 {"input": 0.00015, "output": 0.00060},
    "anthropic:claude-sonnet-4-5-20250929": {"input": 0.003,   "output": 0.015},
    "gemini:gemini-2.5-flash":             {"input": 0.000075, "output": 0.0003},
    "groq:llama-3.3-70b-versatile":        {"input": 0.00059, "output": 0.00079},
}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ChatResult:
    text: str
    provider_used: str
    token_usage: Dict[str, int]
    latency_ms: int
    retry_count: int = 0
    fallback_event: Optional[Dict[str, Any]] = None


@dataclass
class EmbedResult:
    vectors: List[List[float]]
    provider_used: str
    token_usage: Dict[str, int]
    latency_ms: int
    retry_count: int = 0
    fallback_event: Optional[Dict[str, Any]] = None


@dataclass
class ProviderHealth:
    last_call_status: str = "unknown"
    last_latency_ms: int = 0
    last_error: Optional[str] = None
    last_ts: float = 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class AIProviderService:
    """Provider-agnostic chat + embed with failover, retry, and accounting."""

    def __init__(self) -> None:
        self.api_key = os.environ["EMERGENT_LLM_KEY"]
        self.api_base = get_integration_proxy_url() + "/llm"

        # Optional direct keys (groq is the only one wired today).
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()

        primary = os.environ.get("AI_PROVIDER", "openai").strip().lower()
        chain_env = os.environ.get("AI_PROVIDER_CHAIN", "").strip()
        if chain_env:
            chain = [p.strip().lower() for p in chain_env.split(",") if p.strip()]
        else:
            chain = [primary, "anthropic", "gemini"]
        seen: set = set()
        ordered: List[str] = []
        for p in [primary] + chain:
            if p in PROVIDER_DEFAULT_CHAT_MODEL and p not in seen:
                seen.add(p)
                ordered.append(p)
        self.provider_chain: List[str] = ordered

        self.chat_timeout_s = float(os.environ.get("LLM_CHAT_TIMEOUT_S", "30"))
        self.embed_timeout_s = float(os.environ.get("LLM_EMBED_TIMEOUT_S", "15"))
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")

        self._health: Dict[str, ProviderHealth] = {p: ProviderHealth() for p in self.provider_chain}
        self._embed_cache: Dict[str, List[float]] = {}
        self._embed_cache_lock = asyncio.Lock()

        litellm.drop_params = True

        logger.info(
            "ai_provider_initialized",
            extra={
                "provider_chain": self.provider_chain,
                "api_base": self.api_base,
                "embedding_model": self.embedding_model,
                "groq_direct_enabled": bool(self.groq_api_key),
            },
        )

    # --------------------------- Health -----------------------------------
    def health_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            p: {
                "last_call_status": h.last_call_status,
                "last_latency_ms": h.last_latency_ms,
                "last_error": h.last_error,
                "last_ts": h.last_ts,
            }
            for p, h in self._health.items()
        }

    def _mark_health(self, provider: str, ok: bool, latency_ms: int, error: Optional[str]) -> None:
        h = self._health.setdefault(provider, ProviderHealth())
        h.last_call_status = "ok" if ok else "error"
        h.last_latency_ms = latency_ms
        h.last_error = error
        h.last_ts = time.time()

    # --------------------------- Chat -------------------------------------
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        provider_chain: Optional[List[str]] = None,
        agent_name: Optional[str] = None,
    ) -> ChatResult:
        """Run a chat completion with failover across providers.

        Phase AGENTS Step 1: when `json_mode=True`, internally delegates to
        `chat_json()` so JSON parsing + self-correction retry happens uniformly.
        """
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + list(messages)

        if json_mode:
            _parsed, result = await self.chat_json(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                provider_chain=provider_chain,
                agent_name=agent_name,
            )
            return result

        chain = provider_chain or self.provider_chain
        total_retries = 0
        fallback_event: Optional[Dict[str, Any]] = None
        last_error: Optional[str] = None
        primary_provider = chain[0]

        for idx, provider in enumerate(chain):
            t0 = time.perf_counter()
            try:
                text, usage, retries = await self._chat_with_retry(
                    provider=provider,
                    messages=messages,
                    json_mode=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                total_retries += retries
                self._mark_health(provider, ok=True, latency_ms=latency_ms, error=None)
                if idx > 0:
                    fallback_event = {
                        "from_provider": primary_provider,
                        "to_provider": provider,
                        "reason": last_error or "primary_failed",
                    }
                model = PROVIDER_DEFAULT_CHAT_MODEL[provider]
                self._log_usage_safe(
                    kind="chat",
                    provider=provider,
                    model=model,
                    agent_name=agent_name,
                    usage=usage,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                )
                return ChatResult(
                    text=text,
                    provider_used=f"{provider}:{model}",
                    token_usage=usage,
                    latency_ms=latency_ms,
                    retry_count=total_retries,
                    fallback_event=fallback_event,
                )
            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.perf_counter() - t0) * 1000)
                err = f"{type(exc).__name__}: {exc}"
                last_error = err
                self._mark_health(provider, ok=False, latency_ms=latency_ms, error=err)
                self._log_usage_safe(
                    kind="chat",
                    provider=provider,
                    model=PROVIDER_DEFAULT_CHAT_MODEL.get(provider, "unknown"),
                    agent_name=agent_name,
                    usage={"prompt": 0, "completion": 0, "total": 0},
                    latency_ms=latency_ms,
                    success=False,
                    error=err[:300],
                )
                logger.warning(
                    "provider_call_failed",
                    extra={"provider": provider, "error": err, "stage": "chat"},
                )
                continue

        raise RuntimeError(f"All providers failed for chat: {last_error}")

    async def _chat_with_retry(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, Dict[str, int], int]:
        retries = 0
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                return await self._chat_once(
                    provider=provider,
                    messages=messages,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except (asyncio.TimeoutError, ConnectionError) as exc:
                last_exc = exc
                retries += 1
                await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as exc:
                msg = str(exc).lower()
                transient = any(
                    s in msg
                    for s in ("rate limit", "timeout", "503", "502", "504", "overloaded", "temporarily")
                )
                if transient and attempt == 0:
                    last_exc = exc
                    retries += 1
                    await asyncio.sleep(0.5)
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    async def _chat_once(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, Dict[str, int], int]:
        model = PROVIDER_DEFAULT_CHAT_MODEL[provider]

        msgs = list(messages)
        params: Dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": self.chat_timeout_s,
        }

        # Routing: direct Groq if key is provided; otherwise via Emergent proxy.
        if provider == "groq" and self.groq_api_key:
            params["model"] = f"groq/{model}"
            params["api_key"] = self.groq_api_key
            # No api_base => litellm uses Groq's default endpoint.
        else:
            params["api_key"] = self.api_key
            params["api_base"] = self.api_base
            params["custom_llm_provider"] = "openai"  # Emergent proxy speaks OpenAI protocol
            if provider == "gemini":
                params["model"] = f"gemini/{model}"
            if provider == "groq":
                # Attempting groq via Emergent proxy (may not be on the whitelist).
                params["model"] = f"groq/{model}"

        if json_mode and provider in _JSON_MODE_NATIVE:
            params["response_format"] = {"type": "json_object"}
        elif json_mode:
            params["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "You MUST reply with a single valid JSON object only — no prose, no markdown, "
                        "no backticks. Output must be parseable by json.loads."
                    ),
                }
            ] + msgs

        response = await litellm.acompletion(**params)
        text = ""
        if response and response.choices:
            text = response.choices[0].message.content or ""

        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None:
            usage = {
                "prompt": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
                "completion": int(getattr(usage_obj, "completion_tokens", 0) or 0),
                "total": int(getattr(usage_obj, "total_tokens", 0) or 0),
            }
        else:
            usage = {"prompt": 0, "completion": 0, "total": 0}
        return text, usage, 0

    # --------------------------- JSON chat --------------------------------
    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
        provider_chain: Optional[List[str]] = None,
        agent_name: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], ChatResult]:
        """Chat that returns parsed JSON, with 1 self-correction retry."""
        # We re-use the raw chat path (not chat() to avoid recursion via json_mode).
        result = await self._chat_with_failover(
            messages=messages,
            json_mode=True,
            temperature=temperature,
            max_tokens=max_tokens,
            provider_chain=provider_chain,
            agent_name=agent_name,
        )
        parsed = _safe_json_parse(result.text)
        if parsed is not None:
            return parsed, result

        fix_messages = messages + [
            {"role": "assistant", "content": result.text},
            {
                "role": "user",
                "content": (
                    "Your previous response was not valid JSON. Reply with the corrected "
                    "valid JSON object only — no prose, no markdown fences."
                ),
            },
        ]
        result2 = await self._chat_with_failover(
            messages=fix_messages,
            json_mode=True,
            temperature=0.0,
            max_tokens=max_tokens,
            provider_chain=provider_chain,
            agent_name=agent_name,
        )
        result2.retry_count += result.retry_count + 1
        parsed2 = _safe_json_parse(result2.text)
        if parsed2 is None:
            raise ValueError(f"LLM JSON parse failed after retry. Last text: {result2.text[:300]!r}")
        return parsed2, result2

    async def _chat_with_failover(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        provider_chain: Optional[List[str]],
        agent_name: Optional[str],
    ) -> ChatResult:
        """Internal: same loop as chat() but supports json_mode=True directly.

        Kept separate from chat() to avoid recursion when chat_json() drives it.
        """
        chain = provider_chain or self.provider_chain
        total_retries = 0
        fallback_event: Optional[Dict[str, Any]] = None
        last_error: Optional[str] = None
        primary_provider = chain[0]

        for idx, provider in enumerate(chain):
            t0 = time.perf_counter()
            try:
                text, usage, retries = await self._chat_with_retry(
                    provider=provider,
                    messages=messages,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                total_retries += retries
                self._mark_health(provider, ok=True, latency_ms=latency_ms, error=None)
                if idx > 0:
                    fallback_event = {
                        "from_provider": primary_provider,
                        "to_provider": provider,
                        "reason": last_error or "primary_failed",
                    }
                model = PROVIDER_DEFAULT_CHAT_MODEL[provider]
                self._log_usage_safe(
                    kind="chat",
                    provider=provider,
                    model=model,
                    agent_name=agent_name,
                    usage=usage,
                    latency_ms=latency_ms,
                    success=True,
                    error=None,
                )
                return ChatResult(
                    text=text,
                    provider_used=f"{provider}:{model}",
                    token_usage=usage,
                    latency_ms=latency_ms,
                    retry_count=total_retries,
                    fallback_event=fallback_event,
                )
            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.perf_counter() - t0) * 1000)
                err = f"{type(exc).__name__}: {exc}"
                last_error = err
                self._mark_health(provider, ok=False, latency_ms=latency_ms, error=err)
                self._log_usage_safe(
                    kind="chat",
                    provider=provider,
                    model=PROVIDER_DEFAULT_CHAT_MODEL.get(provider, "unknown"),
                    agent_name=agent_name,
                    usage={"prompt": 0, "completion": 0, "total": 0},
                    latency_ms=latency_ms,
                    success=False,
                    error=err[:300],
                )
                logger.warning(
                    "provider_call_failed",
                    extra={"provider": provider, "error": err, "stage": "chat_json"},
                )
                continue
        raise RuntimeError(f"All providers failed for chat: {last_error}")

    # --------------------------- Embed ------------------------------------
    async def embed(
        self,
        texts: List[str],
        agent_name: Optional[str] = None,
    ) -> EmbedResult:
        """Embed a list of strings; uses an in-memory content-hash cache."""
        if not texts:
            return EmbedResult(
                vectors=[],
                provider_used="local:" + _LOCAL_EMBED_MODEL_NAME,
                token_usage={"prompt": 0, "completion": 0, "total": 0},
                latency_ms=0,
            )

        keys = [_hash_text(t) for t in texts]
        cached: Dict[int, List[float]] = {}
        to_embed: List[Tuple[int, str]] = []
        async with self._embed_cache_lock:
            for i, k in enumerate(keys):
                v = self._embed_cache.get(k)
                if v is not None:
                    cached[i] = v
                else:
                    to_embed.append((i, texts[i]))

        usage = {"prompt": 0, "completion": 0, "total": 0}
        latency_ms = 0
        success = True
        error_str: Optional[str] = None
        if to_embed:
            t0 = time.perf_counter()
            try:
                vectors, usage = await self._embed_with_retry([t for _, t in to_embed])
            except Exception as exc:
                success = False
                error_str = f"{type(exc).__name__}: {exc}"
                latency_ms = int((time.perf_counter() - t0) * 1000)
                self._log_usage_safe(
                    kind="embed",
                    provider="local",
                    model=_LOCAL_EMBED_MODEL_NAME,
                    agent_name=agent_name,
                    usage=usage,
                    latency_ms=latency_ms,
                    success=False,
                    error=error_str,
                )
                raise
            latency_ms = int((time.perf_counter() - t0) * 1000)
            async with self._embed_cache_lock:
                for (i, _txt), vec in zip(to_embed, vectors):
                    self._embed_cache[keys[i]] = vec
                    cached[i] = vec

        out_vectors = [cached[i] for i in range(len(texts))]
        provider_label = f"local:{_LOCAL_EMBED_MODEL_NAME}"
        self._log_usage_safe(
            kind="embed",
            provider="local",
            model=_LOCAL_EMBED_MODEL_NAME,
            agent_name=agent_name,
            usage=usage,
            latency_ms=latency_ms,
            success=success,
            error=error_str,
        )
        return EmbedResult(
            vectors=out_vectors,
            provider_used=provider_label,
            token_usage=usage,
            latency_ms=latency_ms,
        )

    async def _embed_with_retry(self, texts: List[str]) -> Tuple[List[List[float]], Dict[str, int]]:
        """Embedding strategy with 2 retries (local backend; see note in docstring).

        PHASE-0 NOTE: the Emergent universal key proxy currently exposes only
        chat models — not embeddings. We use a local model (`BAAI/bge-base-en-v1.5`
        via fastembed/ONNX). These are REAL semantic embeddings.
        """
        delays = [0.5, 1.5]
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                vectors, usage = await asyncio.get_event_loop().run_in_executor(
                    None, _local_embed_sync, texts
                )
                self._mark_health("openai", ok=True, latency_ms=0, error=None)
                return vectors, usage
            except Exception as exc:
                last_exc = exc
                logger.warning("embed_call_failed", extra={"attempt": attempt, "error": str(exc)})
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])
        self._mark_health("openai", ok=False, latency_ms=0, error=str(last_exc))
        assert last_exc is not None
        raise last_exc

    # --------------------------- Usage logging ----------------------------
    def _log_usage_safe(
        self,
        kind: str,
        provider: str,
        model: str,
        agent_name: Optional[str],
        usage: Dict[str, int],
        latency_ms: int,
        success: bool,
        error: Optional[str],
    ) -> None:
        """Fire-and-forget Mongo write to `ai_usage_logs`.

        Scheduled on the event loop so the LLM caller never blocks on logging.
        Failures are swallowed (Mongo hiccup must not break a match run).
        """
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self._log_usage(
                    kind=kind,
                    provider=provider,
                    model=model,
                    agent_name=agent_name,
                    usage=usage,
                    latency_ms=latency_ms,
                    success=success,
                    error=error,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_usage_log_schedule_failed", extra={"error": str(exc)})

    async def _log_usage(
        self,
        kind: str,
        provider: str,
        model: str,
        agent_name: Optional[str],
        usage: Dict[str, int],
        latency_ms: int,
        success: bool,
        error: Optional[str],
    ) -> None:
        # Lazy-import db to avoid a circular import at module load.
        from db import get_db
        tokens_in = int(usage.get("prompt", 0) or 0)
        tokens_out = int(usage.get("completion", 0) or 0)
        total = int(usage.get("total", 0) or (tokens_in + tokens_out))
        cost = _estimate_cost(provider, model, tokens_in, tokens_out)
        doc = {
            "kind": kind,                # "chat" | "embed"
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": total,
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "success": success,
            "error": error,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            db = get_db()
            await db.ai_usage_logs.insert_one(doc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_usage_log_write_failed", extra={"error": str(exc)})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _estimate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> Optional[float]:
    key = f"{provider}:{model}"
    table = COST_PER_1K_TOKENS.get(key)
    if not table:
        return None
    return round(
        (tokens_in / 1000.0) * table["input"] + (tokens_out / 1000.0) * table["output"],
        6,
    )


# ---------------------------------------------------------------------------
# Local embedding backend
# ---------------------------------------------------------------------------
_LOCAL_EMBED_MODEL = None
_LOCAL_EMBED_MODEL_NAME = "BAAI/bge-base-en-v1.5"


def _get_local_embed_model():
    global _LOCAL_EMBED_MODEL
    if _LOCAL_EMBED_MODEL is None:
        from fastembed import TextEmbedding
        _LOCAL_EMBED_MODEL = TextEmbedding(model_name=_LOCAL_EMBED_MODEL_NAME)
        logger.info("local_embed_model_loaded", extra={"model": _LOCAL_EMBED_MODEL_NAME})
    return _LOCAL_EMBED_MODEL


def _local_embed_sync(texts: List[str]) -> Tuple[List[List[float]], Dict[str, int]]:
    model = _get_local_embed_model()
    vectors = [v.tolist() for v in model.embed(texts)]
    total_chars = sum(len(t) for t in texts)
    usage = {"prompt": total_chars // 4, "completion": 0, "total": total_chars // 4}
    return vectors, usage


def _safe_json_parse(text: str) -> Optional[Any]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    if not (s.startswith("{") or s.startswith("[")):
        first_brace = min((idx for idx in (s.find("{"), s.find("[")) if idx >= 0), default=-1)
        if first_brace >= 0:
            s = s[first_brace:]
    try:
        return json.loads(s)
    except Exception:
        return None


# Singleton accessor.
_singleton: Optional[AIProviderService] = None


def get_ai_provider() -> AIProviderService:
    global _singleton
    if _singleton is None:
        _singleton = AIProviderService()
    return _singleton
