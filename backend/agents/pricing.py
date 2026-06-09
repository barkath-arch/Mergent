"""PricingAgent — validates whether a listing's price is fair.

Triggered on solution create/update.
Stores pricing_analysis in solutions collection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Pricing Validator.
Given a software solution and market context, evaluate if the price is fair.

Return ONLY JSON:
{
  "fair": true | false,
  "verdict": "underpriced" | "fair" | "overpriced",
  "suggested_range": {"min_usd": integer, "max_usd": integer},
  "reasoning": "one sentence",
  "price_confidence": "low" | "medium" | "high"
}
JSON only.
"""


class PricingAgent(BaseAgent):
    agent_name = "PricingAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"error": "solution_not_found"}

        # Get category benchmark prices
        db = get_db()
        category = solution.get("category", "")
        benchmarks = []
        if category:
            cursor = db.solutions.find(
                {"category": category, "status": "active", "price_usd": {"$gt": 0}},
                {"price_usd": 1},
            ).limit(20)
            benchmarks = [d["price_usd"] async for d in cursor]

        avg_category_price = sum(benchmarks) / len(benchmarks) if benchmarks else None
        benchmark_context = (
            f"Category average price: ${avg_category_price:.0f} (from {len(benchmarks)} listings)"
            if avg_category_price
            else "No category benchmark available"
        )

        payload = {
            "title": solution.get("title", ""),
            "category": category,
            "tech_stack": solution.get("tech_stack", []),
            "feature_count": len(solution.get("tags", []) or []),
            "deployment_maturity": solution.get("deployment_maturity", ""),
            "current_price_usd": solution.get("price_usd", 0),
            "price_type": solution.get("price_type", ""),
            "benchmark": benchmark_context,
        }

        user_msg = (
            f"Solution to price-check:\n{payload}\n\n"
            "Return pricing validation JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=400,
        )

        if solution_id:
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "pricing_analysis": {
                        **result,
                        "category_avg_price": avg_category_price,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    }
                }},
            )

        return {**result, "_chat_result": chat_result}


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await PricingAgent().execute(ctx, run_id=ctx.get("run_id"))
