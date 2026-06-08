"""ContextCompressionAgent — conditional compression of candidate descriptions.

Phase AGENTS Step 1: subclass of `BaseAgent`; LLM call (when triggered) routed
through `self._llm(json_mode=True)`.
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base import BaseAgent
from db import get_db

COMPRESS_TOKEN_THRESHOLD = 2000


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _build_full_context_text(
    candidates: List[Dict[str, Any]], parsed: Dict[str, Any], user_text: str
) -> str:
    parts: List[str] = []
    parts.append(user_text)
    parts.append(repr(parsed))
    for c in candidates:
        parts.append(c.get("title", ""))
        parts.append(c.get("tagline", ""))
        parts.append(c.get("description", ""))
        parts.append(", ".join(c.get("tech_stack", []) or []))
        parts.append(", ".join(c.get("tags", []) or []))
    return "\n".join(parts)


_COMPRESS_SYSTEM = (
    "You compress software product descriptions for downstream ranking. "
    "Given a JSON list of {id, title, description, tech_stack}, return a JSON object "
    "{compressed: [{id, summary}]} where each `summary` is <=40 words capturing "
    "category, key features, and tech stack. JSON only — no prose."
)


class ContextCompressionAgent(BaseAgent):
    agent_name = "ContextCompressionAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        candidate_ids: List[str] = input.get("candidate_ids", []) or []
        if not candidate_ids:
            return {"compressed": False, "candidates": [], "compression_token_estimate": 0}

        db = get_db()
        docs = [d async for d in db.solutions.find(
            {"_id": {"$in": candidate_ids}},
            {"embedding": 0},
        )]
        by_id = {d["_id"]: d for d in docs}
        candidates = [by_id[sid] for sid in candidate_ids if sid in by_id]

        parsed = input.get("parsed_requirement", {}) or {}
        user_text = input.get("normalized_text", "") or input.get("requirement_text", "")
        full_text = _build_full_context_text(candidates, parsed, user_text)
        token_estimate = _estimate_tokens(full_text)

        if token_estimate <= COMPRESS_TOKEN_THRESHOLD:
            return {
                "compressed": False,
                "candidates": candidates,
                "compression_token_estimate": token_estimate,
            }

        payload = [
            {
                "id": c["_id"],
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "tech_stack": c.get("tech_stack", []),
            }
            for c in candidates
        ]
        user_msg = (
            f"Compress these candidate solutions. Input JSON list:\n{payload}\n"
            "Reply with: {\"compressed\": [{\"id\": ..., \"summary\": ...}]}"
        )
        parsed_resp, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _COMPRESS_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            json_mode=True,
            max_tokens=1200,
        )
        summaries = {item["id"]: item["summary"] for item in parsed_resp.get("compressed", []) if "id" in item}
        for c in candidates:
            if c["_id"] in summaries:
                c["description"] = summaries[c["_id"]]
        return {
            "compressed": True,
            "candidates": candidates,
            "compression_token_estimate": token_estimate,
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ContextCompressionAgent().execute(ctx, run_id=ctx.get("run_id"))
