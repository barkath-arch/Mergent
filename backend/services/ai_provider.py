"""AIProviderService — single LLM/embedding abstraction for MERGENT.

All LLM and embedding calls in the codebase MUST go through this module so that
provider failover, retry, timeout, and token-usage accounting happens uniformly.

Under the hood we use litellm (the same library `emergentintegrations.llm.chat.LlmChat`
uses) and route requests through the Emergent integration proxy when the API key
is the Emergent universal key (`sk-emergent-...`). This gives us OpenAI / Anthropic
/ Gemini access with one credential.

Concurrency: this module is async-only. The class is stateless besides a few
caches (provider health, embedding cache) protected by asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import litellm
from emergentintegrations.llm.utils import get_integration_proxy_url

from services.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider catalogue — kept minimal and explicit. Each entry maps to a
# litellm-compatible model string when calling the Emergent proxy.
# ---------------------------------------------------------------------------
PROVIDER_DEFAULT_CHAT_MODEL: Dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "gemini": "gemini-2.5-flash",
}

# JSON-mode capable models (used by RequirementParser and Ranking).
# OpenAI supports response_format={"type":"json_object"} natively. Anthropic and
# Gemini are coaxed via prompt + parsing.
_JSON_MODE_NATIVE = {"openai"}


# ---------------------------------------------------------------------------
# Public dataclasses returned by the service.
# ---------------------------------------------------------------------------
@dataclass
class ChatResult:
    text: str
    provider_used: str  # "openai:gpt-4o-mini" etc.
    token_usage: Dict[str, int]  # {"prompt":..,"completion":..,"total":..}
    latency_ms: int
    retry_count: int = 0
    fallback_event: Optional[Dict[str, Any]] = None


@dataclass
class EmbedResult:
    vectors: List[List[float]]
    provider_used: str  # "openai:text-embedding-3-large"
    token_usage: Dict[str, int]
    latency_ms: int
    retry_count: int = 0
    fallback_event: Optional[Dict[str, Any]] = None


@dataclass
class ProviderHealth:
    last_call_status: str = "unknown"  # "ok" | "error" | "unknown"
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

        primary = os.environ.get("AI_PROVIDER", "openai").strip().lower()
        chain_env = os.environ.get("AI_PROVIDER_CHAIN", "").strip()
        if chain_env:
            chain = [p.strip().lower() for p in chain_env.split(",") if p.strip()]
        else:
            chain = [primary, "anthropic", "gemini"]
        # Ensure primary is at the head, dedupe while preserving order.
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

        # Set litellm to not modify environment proxy globals.
        litellm.drop_params = True

        logger.info(
            "ai_provider_initialized",
            extra={
                "provider_chain": self.provider_chain,
                "api_base": self.api_base,
                "embedding_model": self.embedding_model,
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
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        provider_chain: Optional[List[str]] = None,
    ) -> ChatResult:
        """Run a chat completion with failover across providers.

        Returns a ChatResult with provider_used, token_usage, latency_ms,
        retry_count, and an optional fallback_event describing the first
        successful fallback transition (if any).
        """
        chain = provider_chain or self.provider_chain
        total_retries = 0
        fallback_event: Optional[Dict[str, Any]] = None
        last_error: Optional[str] = None
        primary_provider = chain[0]

        for idx, provider in enumerate(chain):
            try:
                t0 = time.perf_counter()
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
                return ChatResult(
                    text=text,
                    provider_used=f"{provider}:{PROVIDER_DEFAULT_CHAT_MODEL[provider]}",
                    token_usage=usage,
                    latency_ms=latency_ms,
                    retry_count=total_retries,
                    fallback_event=fallback_event,
                )
            except Exception as exc:  # noqa: BLE001 — provider may raise any exc
                latency_ms = int((time.perf_counter() - t0) * 1000) if "t0" in locals() else 0
                err = f"{type(exc).__name__}: {exc}"
                last_error = err
                self._mark_health(provider, ok=False, latency_ms=latency_ms, error=err)
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
        """One provider, up to 1 retry on transient errors."""
        retries = 0
        last_exc: Optional[Exception] = None
        for attempt in range(2):  # initial + 1 retry
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
                # Retry once on transient-looking errors, otherwise bubble up.
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

        # Build messages, injecting JSON instruction for providers without native JSON mode.
        msgs = list(messages)
        params: Dict[str, Any] = {
            "model": model,  # short model name; api_base routing handles provider
            "messages": msgs,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "custom_llm_provider": "openai",  # Emergent proxy speaks OpenAI protocol
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": self.chat_timeout_s,
        }
        if provider == "gemini":
            # Gemini routed via the emergent proxy keeps the `gemini/` prefix.
            params["model"] = f"gemini/{model}"

        if json_mode and provider in _JSON_MODE_NATIVE:
            params["response_format"] = {"type": "json_object"}
        elif json_mode:
            # Force JSON via system instruction.
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
    ) -> Tuple[Dict[str, Any], ChatResult]:
        """Chat that returns parsed JSON, with 1 self-correction retry."""
        result = await self.chat(
            messages=messages,
            json_mode=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = _safe_json_parse(result.text)
        if parsed is not None:
            return parsed, result

        # Self-correction retry.
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
        result2 = await self.chat(
            messages=fix_messages,
            json_mode=True,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        result2.retry_count += result.retry_count + 1
        parsed2 = _safe_json_parse(result2.text)
        if parsed2 is None:
            raise ValueError(f"LLM JSON parse failed after retry. Last text: {result2.text[:300]!r}")
        return parsed2, result2

    # --------------------------- Embed ------------------------------------
    async def embed(self, texts: List[str]) -> EmbedResult:
        """Embed a list of strings; uses an in-memory content-hash cache."""
        if not texts:
            return EmbedResult(vectors=[], provider_used="openai:" + self.embedding_model,
                               token_usage={"prompt": 0, "completion": 0, "total": 0},
                               latency_ms=0)

        # Check cache, identify cache misses to embed.
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
        if to_embed:
            t0 = time.perf_counter()
            try:
                vectors, usage = await self._embed_with_retry([t for _, t in to_embed])
            finally:
                latency_ms = int((time.perf_counter() - t0) * 1000)
            async with self._embed_cache_lock:
                for (i, _txt), vec in zip(to_embed, vectors):
                    self._embed_cache[keys[i]] = vec
                    cached[i] = vec

        out_vectors = [cached[i] for i in range(len(texts))]
        # Phase-0 compromise: the Emergent proxy doesn't expose embeddings, so
        # we use a local high-quality model under the hood. The provider label
        # reflects the actual backend.
        provider_label = f"local:{_LOCAL_EMBED_MODEL_NAME}"
        return EmbedResult(
            vectors=out_vectors,
            provider_used=provider_label,
            token_usage=usage,
            latency_ms=latency_ms,
        )

    async def _embed_with_retry(self, texts: List[str]) -> Tuple[List[List[float]], Dict[str, int]]:
        """Embedding strategy with 2 retries.

        PHASE-0 NOTE: the Emergent universal key proxy currently exposes only
        chat models — not embeddings. We therefore use a high-quality local
        embedding model (`BAAI/bge-base-en-v1.5` via fastembed/ONNX) as the
        backend. These are REAL semantic embeddings (768-dim, dense, learned),
        not mocked vectors. Cosine similarity ranking against them is real
        semantic search. See MIGRATION_NOTES.md for the swap-path to OpenAI's
        `text-embedding-3-large` when a real OpenAI key is available.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Local embedding backend (Phase 0 compromise — see _embed_with_retry docstring)
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
    # Rough token-equivalent (4 chars/token).
    total_chars = sum(len(t) for t in texts)
    usage = {"prompt": total_chars // 4, "completion": 0, "total": total_chars // 4}
    return vectors, usage


def _safe_json_parse(text: str) -> Optional[Any]:
    if not text:
        return None
    s = text.strip()
    # Strip markdown fences if any LLM ignored instructions.
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    # Find first { and last } if there is surrounding prose.
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
