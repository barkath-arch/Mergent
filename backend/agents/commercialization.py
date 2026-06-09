"""CommercializationAgent — recommends licensing model and commercial approach.

Triggered on solution create/update.
Stores result in solutions.commercialization_details (JSON).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Commercialization Advisor.
Analyze a software solution and recommend the best commercial approach for the builder.

Return ONLY JSON:
{
  "recommended_licensing": "saas_subscription" | "one_time" | "white_label" | "source_code" | "hybrid",
  "white_label_score": 0-100,
  "customization_ease": "low" | "medium" | "high",
  "target_buyer_size": "startup" | "smb" | "enterprise" | "all",
  "deployment_suitability": "cloud" | "on_premise" | "both",
  "suggested_price_range": {"min_usd": integer, "max_usd": integer},
  "market_positioning": "one sentence on how to position this solution",
  "upsell_opportunities": ["potential add-on 1", "potential add-on 2"],
  "go_to_market_hint": "one sentence on best channel to sell this"
}
JSON only.
"""


class CommercializationAgent(BaseAgent):
    agent_name = "CommercializationAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"error": "solution_not_found"}

        payload = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tech_stack": solution.get("tech_stack", []),
            "tags": solution.get("tags", []),
            "current_price": solution.get("price_usd", 0),
            "current_price_type": solution.get("price_type", ""),
            "deployment_maturity": solution.get("deployment_maturity", ""),
            "deployed_count": solution.get("deployed_count", 0),
        }

        user_msg = (
            f"Software solution to analyze:\n{payload}\n\n"
            "Return commercialization recommendation JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            json_mode=True,
            max_tokens=600,
        )

        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "commercialization_details": {
                        **result,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    }
                }},
            )

        return {**result, "_chat_result": chat_result}


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await CommercializationAgent().execute(ctx, run_id=ctx.get("run_id"))
