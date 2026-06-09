"""AcquisitionAdvisorAgent — synthesizes all signals into a final recommendation.

Called at the end of the match pipeline for the top 3 results.
Shown as "MERGENT Recommends" card on solution detail page.

POST /api/solutions/{id}/advise
"""
from __future__ import annotations

from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Acquisition Advisor — the final decision layer.
You synthesize match score, trust score, ROI analysis, and reflection signals
to give a buyer a clear, honest acquisition recommendation.

Be direct. Buyers need clarity, not hedging.

Return ONLY JSON:
{
  "recommend": true | false,
  "confidence": "high" | "medium" | "low",
  "verdict": "strong_buy" | "buy" | "consider" | "avoid",
  "summary": "2 sentences max — direct verdict with key reason",
  "next_steps": ["action 1", "action 2", "action 3"],
  "risk_flags": ["risk 1", "risk 2"] or [],
  "deal_breakers": ["critical issue 1"] or [],
  "strengths": ["strength 1", "strength 2"]
}
JSON only.
"""


class AcquisitionAdvisorAgent(BaseAgent):
    agent_name = "AcquisitionAdvisorAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        match_score = input.get("match_score", 0)
        trust_score = input.get("trust_score") or solution.get("trust_score", 50)
        roi_result = input.get("roi_result", {}) or {}
        reflection_result = input.get("reflection_result", {}) or {}
        requirement_text = input.get("requirement_text", "")

        signals = {
            "match_score": match_score,
            "match_explanation": input.get("match_explanation", ""),
            "trust_score": trust_score,
            "trust_flags": solution.get("trust_score_details", {}).get("flags", []),
            "roi_recommendation": roi_result.get("recommendation", ""),
            "build_cost_usd": roi_result.get("build_cost_usd"),
            "acquisition_cost_usd": roi_result.get("acquisition_cost_usd") or solution.get("price_usd", 0),
            "payback_months": roi_result.get("payback_months"),
            "reflection_approved": reflection_result.get("reflection_approved", True),
            "reflection_concern": reflection_result.get("reflection_concern"),
            "reflection_severity": reflection_result.get("reflection_severity", "none"),
            "missing_critical_features": reflection_result.get("missing_critical_features", []),
            "solution_title": solution.get("title", ""),
            "solution_category": solution.get("category", ""),
            "builder_rating": solution.get("builder_rating", 0),
            "uptime_pct": solution.get("uptime_pct", 0),
            "deployed_count": solution.get("deployed_count", 0),
        }

        user_msg = (
            f"Buyer requirement:\n{requirement_text}\n\n"
            f"All signals for acquisition decision:\n{signals}\n\n"
            "Return acquisition recommendation JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=700,
        )

        # Persist to solution if solution_id provided
        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {"acquisition_advice": result}},
            )

        return {**result, "_chat_result": chat_result}


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await AcquisitionAdvisorAgent().execute(ctx, run_id=ctx.get("run_id"))
