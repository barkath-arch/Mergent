"""TrustAuditorAgent — scores every listing on trustworthiness.

Triggered on solution create/update. Stores result in:
  solutions.trust_score (int 0-100)
  solutions.trust_score_details (JSON)

Score display rules:
  >= 80  → green badge
  50-79  → amber badge
  < 50   → red badge (flagged for review)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Trust Auditor. Evaluate a software listing for trustworthiness.

Score 0-100 across three dimensions:
1. Completeness (0-100): Does the listing have a title, description, tags, demo URL, tech stack, screenshots?
2. Credibility (0-100): Does the builder have a profile, reviews, deployment history, realistic claims?
3. Red Flags (0-100, where 100 = NO red flags): Check for: vague descriptions, unrealistic uptime claims,
   no demo URL, suspicious pricing (too cheap or too expensive for the category), plagiarized content signals.

Overall score = (completeness * 0.35) + (credibility * 0.35) + (red_flags * 0.30)

Return ONLY JSON:
{
  "score": 0-100,
  "breakdown": {
    "completeness": 0-100,
    "credibility": 0-100,
    "red_flags": 0-100
  },
  "flags": ["list of specific concerns — be concrete, not generic"],
  "summary": "one sentence verdict",
  "recommended_action": "none" | "warn_builder" | "require_review" | "reject"
}
JSON only. No prose.
"""


class TrustAuditorAgent(BaseAgent):
    agent_name = "TrustAuditorAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"trust_score": 0, "trust_score_details": {}, "error": "solution_not_found"}

        # Build builder context if available
        builder_context: Dict[str, Any] = {}
        builder_id = solution.get("builder_id")
        if builder_id:
            db = get_db()
            builder = await db.builder_profiles.find_one({"user_id": builder_id}) or {}
            review_count = await db.reviews.count_documents({"builder_id": builder_id})
            transaction_count = await db.transactions.count_documents({"builder_id": builder_id})
            builder_context = {
                "verified": builder.get("verified", False),
                "rating": builder.get("rating", 0),
                "review_count": review_count,
                "transaction_count": transaction_count,
                "account_age_days": (
                    (datetime.now(timezone.utc) - builder.get("created_at", datetime.now(timezone.utc))).days
                    if builder.get("created_at") else 0
                ),
            }

        listing_payload = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tags": solution.get("tags", []),
            "tech_stack": solution.get("tech_stack", []),
            "price_usd": solution.get("price_usd", 0),
            "price_type": solution.get("price_type", ""),
            "demo_url": bool(solution.get("demo_url")),
            "preview_image_count": len(solution.get("preview_images", []) or []),
            "uptime_pct": solution.get("uptime_pct", 0),
            "deployed_count": solution.get("deployed_count", 0),
            "builder": builder_context,
        }

        user_msg = (
            f"Software listing to audit:\n{listing_payload}\n\n"
            "Return the trust audit JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=600,
        )

        score = max(0, min(100, int(result.get("score", 50))))
        details = {
            "breakdown": result.get("breakdown", {}),
            "flags": result.get("flags", []),
            "summary": result.get("summary", ""),
            "recommended_action": result.get("recommended_action", "none"),
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist to DB if solution_id provided
        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "trust_score": score,
                    "trust_score_details": details,
                    "trust_audited_at": datetime.now(timezone.utc),
                }},
            )

            # Flag for admin review if score < 40 or action requires it
            action = result.get("recommended_action", "none")
            if action in ("require_review", "reject") or score < 40:
                await db.admin_flags.insert_one({
                    "entity_type": "solution",
                    "entity_id": solution_id,
                    "reason": f"Trust audit: {result.get('summary', '')}",
                    "severity": "high" if score < 40 else "medium",
                    "flags": result.get("flags", []),
                    "recommended_action": action,
                    "created_at": datetime.now(timezone.utc),
                })

        return {
            "trust_score": score,
            "trust_score_details": details,
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await TrustAuditorAgent().execute(ctx, run_id=ctx.get("run_id"))
