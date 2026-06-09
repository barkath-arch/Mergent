"""FraudAgent — detects manipulation signals across solutions, reviews, and builders.

Triggers:
  - New review submitted
  - New builder registers
  - Solution with abnormally high stats listed

Flags entities to admin_flags table.
Suspends entity if action=suspend.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Fraud Detection Agent.
Analyze the provided entity for manipulation, fake activity, or abuse signals.

For REVIEW entities, check:
- Suspiciously short/generic text ("Great product!", "5 stars!")
- Reviewer with no purchase history reviewing the product
- Multiple reviews from same IP or same day
- Rating inconsistent with review text sentiment

For BUILDER entities, check:
- Recently created account with many listings
- Duplicate accounts (same email pattern, same listing titles)
- Claimed stats (uptime, clients) inconsistent with account age
- Profile photo/bio copied from other platforms

For SOLUTION entities, check:
- Claimed metrics (uptime %, client count) implausibly high for new listing
- Description copied/plagiarized
- Price significantly outside category norms
- No verifiable demo URL but claims production deployments

Return ONLY JSON:
{
  "is_suspicious": true | false,
  "signals": ["specific signal 1", "specific signal 2"],
  "severity": "low" | "medium" | "high",
  "action": "none" | "flag" | "suspend",
  "reasoning": "one sentence"
}
JSON only.
"""


class FraudAgent(BaseAgent):
    agent_name = "FraudAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        entity_type = input.get("entity_type", "solution")
        entity_id = input.get("entity_id")
        entity_data = input.get("entity_data", {}) or {}

        db = get_db()

        # Enrich entity data with context
        context: Dict[str, Any] = {"entity_type": entity_type, **entity_data}

        if entity_type == "review":
            review = entity_data or await db.reviews.find_one({"_id": entity_id}) or {}
            buyer_id = review.get("buyer_id")
            prior_reviews = await db.reviews.count_documents({"buyer_id": buyer_id}) if buyer_id else 0
            purchases = await db.transactions.count_documents({"buyer_id": buyer_id}) if buyer_id else 0
            # Check for multiple reviews same day
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            same_day_reviews = await db.reviews.count_documents({
                "buyer_id": buyer_id,
                "created_at": {"$gte": today_start},
            }) if buyer_id else 0
            context.update({
                "reviewer_prior_reviews": prior_reviews,
                "reviewer_purchase_count": purchases,
                "same_day_review_count": same_day_reviews,
                "review_text": review.get("comment", ""),
                "rating": review.get("rating", 0),
            })

        elif entity_type == "builder":
            builder = entity_data or await db.builder_profiles.find_one({"user_id": entity_id}) or {}
            listing_count = await db.solutions.count_documents({"builder_id": entity_id}) if entity_id else 0
            account_age_days = 0
            if builder.get("created_at"):
                account_age_days = (datetime.now(timezone.utc) - builder["created_at"]).days
            context.update({
                "listing_count": listing_count,
                "account_age_days": account_age_days,
                "claimed_rating": builder.get("rating", 0),
                "claimed_clients": builder.get("total_clients", 0),
                "verified": builder.get("verified", False),
            })

        elif entity_type == "solution":
            solution = entity_data or await db.solutions.find_one({"_id": entity_id}) or {}
            builder_id = solution.get("builder_id")
            builder_age_days = 0
            if builder_id:
                bp = await db.builder_profiles.find_one({"user_id": builder_id}) or {}
                if bp.get("created_at"):
                    builder_age_days = (datetime.now(timezone.utc) - bp["created_at"]).days
            context.update({
                "claimed_uptime_pct": solution.get("uptime_pct", 0),
                "claimed_deployed_count": solution.get("deployed_count", 0),
                "builder_account_age_days": builder_age_days,
                "has_demo_url": bool(solution.get("demo_url")),
                "price_usd": solution.get("price_usd", 0),
            })

        user_msg = f"Entity to analyze:\n{context}\n\nReturn fraud analysis JSON now."

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=500,
        )

        is_suspicious = bool(result.get("is_suspicious", False))
        action = result.get("action", "none")
        severity = result.get("severity", "low")

        if action in ("flag", "suspend") and entity_id:
            await db.admin_flags.insert_one({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "reason": result.get("reasoning", "Fraud signals detected"),
                "signals": result.get("signals", []),
                "severity": severity,
                "action": action,
                "created_at": datetime.now(timezone.utc),
                "resolved": False,
            })

        if action == "suspend" and entity_id:
            collection_map = {
                "solution": db.solutions,
                "builder": db.builder_profiles,
                "review": db.reviews,
            }
            coll = collection_map.get(entity_type)
            if coll is not None:
                await coll.update_one(
                    {"_id": entity_id},
                    {"$set": {"status": "suspended", "suspended_at": datetime.now(timezone.utc)}},
                )

        return {
            "is_suspicious": is_suspicious,
            "signals": result.get("signals", []),
            "severity": severity,
            "action": action,
            "reasoning": result.get("reasoning", ""),
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await FraudAgent().execute(ctx, run_id=ctx.get("run_id"))
