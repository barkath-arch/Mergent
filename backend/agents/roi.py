"""ROIAgent — calculates build-vs-buy ROI for a solution.

Triggered when buyer clicks "Calculate ROI" on solution detail page.
Results cached per solution+requirement combo for 24h.

POST /api/solutions/{id}/roi  body: {requirement_text}
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

HOURLY_RATE_USD = 75  # build cost assumption

_SYSTEM_PROMPT = f"""You are MERGENT's ROI Calculator.
Given a buyer's software requirement and a solution they are considering acquiring,
calculate the financial case for buying vs building from scratch.

Assumptions:
- Engineering hourly rate: ${HOURLY_RATE_USD}/hr
- Include design, testing, deployment, and maintenance in build estimate
- Be realistic — don't underestimate build complexity

Return ONLY JSON:
{{
  "build_hours": integer,
  "build_cost_usd": integer (build_hours * {HOURLY_RATE_USD}),
  "time_to_market_weeks": integer,
  "acquisition_cost_usd": integer,
  "monthly_maintenance_cost_usd": integer (ongoing cost if built),
  "payback_months": float (how long until acquisition pays for itself vs build),
  "roi_percentage": float (return on investment over 12 months),
  "recommendation": "acquire" | "consider" | "build",
  "reasoning": "2 sentences max explaining the recommendation",
  "risk_factors": ["build risk 1", "build risk 2"]
}}
JSON only.
"""


class ROIAgent(BaseAgent):
    agent_name = "ROIAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")
        requirement_text = input.get("requirement_text", "") or ""

        db = get_db()

        if not solution and solution_id:
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"error": "solution_not_found"}

        # Check cache
        cache_key = f"{solution_id}_{hash(requirement_text[:100])}"
        cached = await db.roi_cache.find_one({"cache_key": cache_key})
        if cached:
            cache_age = datetime.now(timezone.utc) - cached.get("created_at", datetime.min.replace(tzinfo=timezone.utc))
            if cache_age < timedelta(hours=24):
                return {**cached.get("result", {}), "from_cache": True}

        solution_summary = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tech_stack": solution.get("tech_stack", []),
            "price_usd": solution.get("price_usd", 0),
            "price_type": solution.get("price_type", "one_time"),
            "deployment_maturity": solution.get("deployment_maturity", ""),
            "features": solution.get("tags", []),
        }

        user_msg = (
            f"Buyer requirement:\n{requirement_text}\n\n"
            f"Solution being considered:\n{solution_summary}\n\n"
            "Calculate ROI JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=700,
        )

        # Ensure acquisition_cost_usd is set from solution price if LLM missed it
        if not result.get("acquisition_cost_usd"):
            result["acquisition_cost_usd"] = solution.get("price_usd", 0)

        # Persist to cache
        await db.roi_cache.replace_one(
            {"cache_key": cache_key},
            {
                "cache_key": cache_key,
                "solution_id": solution_id,
                "result": result,
                "created_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )

        return {**result, "from_cache": False, "_chat_result": chat_result}


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ROIAgent().execute(ctx, run_id=ctx.get("run_id"))
