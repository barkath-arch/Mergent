"""ReputationAgent — aggregates builder reputation score from multiple signals.

Pure aggregation — no LLM call. Runs after:
  - Transaction completion
  - Review submission
  - Deployment health update

Stores result in builder_profiles.reputation_score (0-100).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

# Weight configuration
WEIGHTS = {
    "avg_review_rating": 0.35,    # 5-star scale normalized to 0-100
    "transaction_completion_rate": 0.25,  # completed / total
    "avg_uptime_percent": 0.20,   # from deployments
    "response_time_score": 0.10,  # hours to reply, inverted
    "account_age_score": 0.10,    # days / 365, capped at 1.0
}

MAX_RESPONSE_HOURS = 72  # 72h response = score 0, 1h = score ~98


class ReputationAgent(BaseAgent):
    agent_name = "ReputationAgent"
    agent_version = "1.0.0"

    # No LLM — override _llm usage entirely
    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        builder_id = input.get("builder_id")
        if not builder_id:
            return {"reputation_score": 0, "error": "builder_id_required"}

        db = get_db()

        # 1. Average review rating (normalized 0-100)
        reviews = [d async for d in db.reviews.find({"builder_id": builder_id}, {"rating": 1})]
        if reviews:
            avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews)
            review_score = (avg_rating / 5.0) * 100
        else:
            review_score = 50.0  # neutral default for new builders

        # 2. Transaction completion rate
        total_txns = await db.transactions.count_documents({"builder_id": builder_id})
        completed_txns = await db.transactions.count_documents({
            "builder_id": builder_id,
            "status": "completed",
        })
        txn_rate = (completed_txns / total_txns * 100) if total_txns > 0 else 50.0

        # 3. Average uptime from deployments
        deployments = [d async for d in db.deployments.find(
            {"builder_id": builder_id, "status": "live"},
            {"uptime_percent": 1},
        )]
        if deployments:
            avg_uptime = sum(d.get("uptime_percent", 0) for d in deployments) / len(deployments)
        else:
            avg_uptime = 50.0

        # 4. Response time score (from messages)
        # Average hours to first response on conversation threads
        convos = [d async for d in db.conversations.find(
            {"builder_id": builder_id},
            {"first_response_hours": 1},
        ).limit(20)]
        if convos and any(c.get("first_response_hours") for c in convos):
            avg_hours = sum(
                c.get("first_response_hours", MAX_RESPONSE_HOURS)
                for c in convos
                if c.get("first_response_hours") is not None
            ) / max(1, sum(1 for c in convos if c.get("first_response_hours") is not None))
            response_score = max(0.0, (1 - avg_hours / MAX_RESPONSE_HOURS) * 100)
        else:
            response_score = 50.0

        # 5. Account age score (capped at 1 year = 100)
        profile = await db.builder_profiles.find_one({"user_id": builder_id}) or {}
        created_at = profile.get("created_at")
        if created_at:
            age_days = (datetime.now(timezone.utc) - created_at).days
            age_score = min(100.0, (age_days / 365) * 100)
        else:
            age_score = 0.0

        # Weighted aggregate
        reputation_score = round(
            review_score * WEIGHTS["avg_review_rating"]
            + txn_rate * WEIGHTS["transaction_completion_rate"]
            + avg_uptime * WEIGHTS["avg_uptime_percent"]
            + response_score * WEIGHTS["response_time_score"]
            + age_score * WEIGHTS["account_age_score"],
            1,
        )
        reputation_score = max(0.0, min(100.0, reputation_score))

        breakdown = {
            "review_score": round(review_score, 1),
            "transaction_completion_rate": round(txn_rate, 1),
            "avg_uptime": round(avg_uptime, 1),
            "response_time_score": round(response_score, 1),
            "account_age_score": round(age_score, 1),
            "review_count": len(reviews),
            "transaction_count": total_txns,
        }

        # Persist
        await db.builder_profiles.update_one(
            {"user_id": builder_id},
            {"$set": {
                "reputation_score": reputation_score,
                "reputation_breakdown": breakdown,
                "reputation_updated_at": datetime.now(timezone.utc),
            }},
        )

        return {
            "builder_id": builder_id,
            "reputation_score": reputation_score,
            "breakdown": breakdown,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ReputationAgent().execute(ctx, run_id=ctx.get("run_id"))
