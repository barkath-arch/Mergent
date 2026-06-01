"""EmbeddingAgent — compute query embedding via AIProviderService.embed."""
from __future__ import annotations

from typing import Any, Dict

from services.ai_provider import get_ai_provider


def _build_requirement_summary(ctx: Dict[str, Any]) -> str:
    """Compose a compact text used as the embedding input.

    Combines the user's normalized requirement with parser-extracted features so
    that semantic search has rich context to match against.
    """
    parsed = ctx.get("parsed_requirement", {}) or {}
    parts = [ctx.get("normalized_text", "")]
    cat = parsed.get("category")
    domain = parsed.get("business_domain")
    feats = parsed.get("required_features") or []
    tech = parsed.get("tech_preferences") or []
    if cat:
        parts.append(f"Category: {cat}")
    if domain:
        parts.append(f"Domain: {domain}")
    if feats:
        parts.append(f"Features: {', '.join(feats)}")
    if tech:
        parts.append(f"Tech preferences: {', '.join(tech)}")
    return "\n".join(p for p in parts if p)


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    provider = get_ai_provider()
    summary = _build_requirement_summary(ctx)
    result = await provider.embed([summary])
    return {
        "requirement_summary": summary,
        "query_vector": result.vectors[0] if result.vectors else [],
        "_embed_result": result,
    }
