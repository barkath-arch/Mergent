"""RankingAgent — LLM-driven scoring of candidate solutions vs parsed requirement.

Phase AGENTS Step 1: subclass of `BaseAgent`; LLM call routed through
`self._llm(json_mode=True)`. Determinism (temperature=0 + stable tiebreaker by
vector similarity) is preserved.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError, field_validator

from agents.base import BaseAgent

_SYSTEM_PROMPT = """You are MERGENT's RankingAgent.
Given a parsed software requirement and a list of candidate solutions, produce a JSON ranking.

Return ONLY a JSON object of this shape (no prose, no markdown):
{
  "rankings": [
    {
      "solutionId": "string — must match one of the candidate IDs exactly",
      "score": 0..100,
      "explanation": "1-2 sentences referencing concrete fields like tech_stack overlap, category match, deployment maturity, or specific features",
      "confidence": "low" | "medium" | "high"
    }
  ]
}

Scoring rubric:
- 90-100: direct category match + tech_stack overlap + required features fulfilled
- 70-89: strong category match, partial feature/tech overlap
- 50-69: adjacent category or major partial fit
- below 50: weak fit; only include if no better candidates exist

Order rankings from highest score to lowest. Include every candidate in the input.
"""


class _Rank(BaseModel):
    solutionId: str
    score: float = Field(ge=0, le=100)
    explanation: str
    confidence: str

    @field_validator("confidence")
    @classmethod
    def _confidence_norm(cls, v: str) -> str:
        v2 = (v or "medium").lower().strip()
        if v2 not in ("low", "medium", "high"):
            return "medium"
        return v2


def _build_candidate_block(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in candidates:
        out.append(
            {
                "id": c["_id"],
                "title": c.get("title", ""),
                "tagline": c.get("tagline", ""),
                "description": c.get("description", ""),
                "category": c.get("category", ""),
                "tech_stack": c.get("tech_stack", []),
                "tags": c.get("tags", []),
                "deployment_maturity": c.get("deployment_maturity", ""),
                "price_usd": c.get("price_usd", 0),
                "license_model": c.get("license_model", ""),
                "builder_rating": c.get("builder_rating", 0),
                "uptime_pct": c.get("uptime_pct", 0),
                "clients_count": c.get("clients_count", 0),
            }
        )
    return out


class RankingAgent(BaseAgent):
    agent_name = "RankingAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        candidates: List[Dict[str, Any]] = input.get("candidates", []) or []
        if not candidates:
            return {"ranked": [], "rerank_latency_ms": 0}

        parsed = input.get("parsed_requirement", {}) or {}
        cand_block = _build_candidate_block(candidates)
        candidates_meta = input.get("candidates_meta", []) or []
        sim_by_id = {m["solution_id"]: m.get("vector_score", 0.0) for m in candidates_meta}

        user_msg = (
            f"Parsed requirement:\n{parsed}\n\n"
            f"Candidate solutions ({len(cand_block)}):\n{cand_block}\n\n"
            "Return the ranking JSON now."
        )
        parsed_resp, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            json_mode=True,
            max_tokens=2500,
        )

        raw_rankings = parsed_resp.get("rankings", [])
        if not isinstance(raw_rankings, list):
            raw_rankings = []

        valid_ids = {c["_id"] for c in candidates}
        ranked: List[Dict[str, Any]] = []
        for entry in raw_rankings:
            try:
                r = _Rank(**entry)
            except ValidationError:
                continue
            if r.solutionId not in valid_ids:
                continue
            ranked.append(
                {
                    "solutionId": r.solutionId,
                    "score": float(r.score),
                    "explanation": r.explanation,
                    "confidence": r.confidence,
                }
            )

        present = {r["solutionId"] for r in ranked}
        for c in candidates:
            if c["_id"] not in present:
                ranked.append(
                    {
                        "solutionId": c["_id"],
                        "score": 30.0,
                        "explanation": (
                            f"Fallback ranking — model omitted this candidate. "
                            f"Tech stack: {', '.join(c.get('tech_stack', []))}. "
                            f"Category: {c.get('category', '')}."
                        ),
                        "confidence": "low",
                    }
                )

        ranked.sort(key=lambda r: (-r["score"], -sim_by_id.get(r["solutionId"], 0.0)))
        return {
            "ranked": ranked,
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await RankingAgent().execute(ctx, run_id=ctx.get("run_id"))
