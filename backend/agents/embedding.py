"""EmbeddingAgent — compute query embedding via the AI provider.

Phase AGENTS Step 1: subclass of `BaseAgent`; embed call routed through
`self._embed()` so `ai_usage_logs` records `agent_name`.
"""
from __future__ import annotations

from typing import Any, Dict

from agents.base import BaseAgent


def _build_requirement_summary(ctx: Dict[str, Any]) -> str:
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


class EmbeddingAgent(BaseAgent):
    agent_name = "EmbeddingAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        summary = _build_requirement_summary(input)
        vec, result = await self._embed(summary)
        return {
            "requirement_summary": summary,
            "query_vector": vec,
            "_embed_result": result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await EmbeddingAgent().execute(ctx, run_id=ctx.get("run_id"))
