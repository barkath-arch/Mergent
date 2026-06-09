"""Forking Layer Agents — the biggest MERGENT differentiator.

ForkingAgent           — generates detailed fork plan from buyer request
SimilarityAgent        — finds similar solutions as alternatives
CloneIntelligenceAgent — analyzes reuse potential
ReusabilityAgent       — calculates effort and cost

Full forking flow:
  POST /api/solutions/{id}/fork
    → ForkingAgent
    → CloneIntelligenceAgent
    → ReusabilityAgent
    → SimilarityAgent
    → Return complete fork_result
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from agents.base import BaseAgent
from db import get_db


# ─────────────────────────────────────────────────────────────────────────────
# Forking Agent
# ─────────────────────────────────────────────────────────────────────────────

_FORK_SYSTEM = """You are MERGENT's Forking Advisor.
A buyer wants to customize an existing software solution for their specific needs.
Generate a detailed, actionable fork plan.

Return ONLY JSON:
{
  "features_to_keep": ["feature 1", "feature 2"],
  "features_to_modify": [
    {"feature": "feature name", "change_description": "what needs to change"}
  ],
  "features_to_add": [
    {"feature": "feature name", "effort": "low" | "medium" | "high", "estimated_hours": integer}
  ],
  "features_to_remove": ["feature to remove 1"],
  "total_estimated_hours": integer,
  "reuse_percentage": 0-100,
  "recommended_approach": "2 sentences on how to execute this fork",
  "complexity": "simple" | "moderate" | "complex",
  "tech_challenges": ["challenge 1", "challenge 2"],
  "recommended_tech_changes": ["tech change 1"]
}
JSON only."""


class ForkingAgent(BaseAgent):
    agent_name = "ForkingAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")
        customization_request: str = input.get("customization_request", "")
        buyer_id: str = input.get("buyer_id", "")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution or not customization_request:
            return {"error": "solution and customization_request required"}

        solution_summary = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tech_stack": solution.get("tech_stack", []),
            "tags": solution.get("tags", []),
            "features": solution.get("features", []),
        }

        user_msg = (
            f"Original solution:\n{solution_summary}\n\n"
            f"Buyer customization request:\n{customization_request}\n\n"
            "Generate the fork plan JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _FORK_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            json_mode=True,
            max_tokens=1000,
        )

        # Save fork request to DB
        db = get_db()
        fork_doc = {
            "solution_id": solution_id,
            "buyer_id": buyer_id,
            "customization_request": customization_request,
            "fork_plan_json": result,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }
        insert_result = await db.fork_requests.insert_one(fork_doc)
        fork_request_id = str(insert_result.inserted_id)

        # Notify builder
        builder_id = solution.get("builder_id")
        if builder_id:
            await db.notifications.insert_one({
                "user_id": builder_id,
                "type": "fork_request",
                "message": f"New fork request on '{solution.get('title', '')}' — buyer wants to customize it.",
                "link": f"/fork-requests/{fork_request_id}",
                "read": False,
                "created_at": datetime.now(timezone.utc),
            })

        return {
            **result,
            "fork_request_id": fork_request_id,
            "_chat_result": chat_result,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Similarity Agent
# ─────────────────────────────────────────────────────────────────────────────

_SIM_SYSTEM = """You are MERGENT's Similarity Advisor.
Compare two software solutions and explain why the second might be a better fork candidate.
Return ONLY JSON:
{
  "reason": "one sentence why this alternative might need less customization",
  "effort_comparison": "less" | "same" | "more",
  "key_overlap": ["shared feature 1", "shared feature 2"]
}
JSON only."""


class SimilarityAgent(BaseAgent):
    agent_name = "SimilarityAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")
        top_n: int = input.get("top_n", 3)
        customization_request: str = input.get("customization_request", "")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"similar_solutions": []}

        db = get_db()
        category = solution.get("category", "")

        # Find similar solutions in same category
        cursor = db.solutions.find(
            {
                "category": category,
                "status": "active",
                "_id": {"$ne": solution_id},
            },
            {"title": 1, "description": 1, "tech_stack": 1, "tags": 1, "price_usd": 1},
        ).limit(10)
        candidates = [d async for d in cursor]

        if not candidates:
            return {"similar_solutions": []}

        similar_solutions: List[Dict[str, Any]] = []
        for candidate in candidates[:top_n]:
            comparison = {
                "original": {
                    "title": solution.get("title", ""),
                    "tech_stack": solution.get("tech_stack", []),
                    "tags": solution.get("tags", []),
                },
                "alternative": {
                    "title": candidate.get("title", ""),
                    "tech_stack": candidate.get("tech_stack", []),
                    "tags": candidate.get("tags", []),
                },
                "buyer_request": customization_request,
            }

            result, _ = await self._llm(
                messages=[
                    {"role": "system", "content": _SIM_SYSTEM},
                    {"role": "user", "content": f"Compare these solutions:\n{comparison}\n\nReturn JSON now."},
                ],
                temperature=0.2,
                json_mode=True,
                max_tokens=300,
            )

            similar_solutions.append({
                "solution_id": str(candidate["_id"]),
                "title": candidate.get("title", ""),
                "price_usd": candidate.get("price_usd", 0),
                "reason": result.get("reason", ""),
                "effort_comparison": result.get("effort_comparison", "same"),
                "key_overlap": result.get("key_overlap", []),
            })

        return {"similar_solutions": similar_solutions}


# ─────────────────────────────────────────────────────────────────────────────
# Clone Intelligence Agent
# ─────────────────────────────────────────────────────────────────────────────

_CLONE_SYSTEM = """You are MERGENT's Clone Intelligence system.
Analyze a fork plan and determine what can be reused vs needs rebuilding.
Return ONLY JSON:
{
  "reusable_modules": ["module/component that can be kept as-is"],
  "rebuild_required": ["module/component that needs full rebuild"],
  "partially_reusable": ["module that needs modification but not full rebuild"],
  "reuse_score": 0-100,
  "lineage_notes": "one sentence on the reuse strategy",
  "recommended_base": "use_as_is" | "needs_significant_changes" | "rebuild_recommended",
  "estimated_reuse_hours_saved": integer
}
JSON only."""


class CloneIntelligenceAgent(BaseAgent):
    agent_name = "CloneIntelligenceAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        fork_plan = input.get("fork_plan", {}) or {}

        if not fork_plan:
            return {"reuse_score": 50, "recommended_base": "needs_significant_changes"}

        analysis_input = {
            "solution_tech_stack": solution.get("tech_stack", []),
            "solution_category": solution.get("category", ""),
            "fork_plan": {
                "features_to_keep": fork_plan.get("features_to_keep", []),
                "features_to_modify": fork_plan.get("features_to_modify", []),
                "features_to_add": fork_plan.get("features_to_add", []),
                "reuse_percentage": fork_plan.get("reuse_percentage", 50),
                "complexity": fork_plan.get("complexity", "moderate"),
            },
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _CLONE_SYSTEM},
                {"role": "user", "content": f"Analyze fork plan:\n{analysis_input}\n\nReturn JSON now."},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=700,
        )

        # Update fork_request if id provided
        fork_request_id = input.get("fork_request_id")
        if fork_request_id:
            db = get_db()
            await db.fork_requests.update_one(
                {"_id": fork_request_id},
                {"$set": {"clone_intelligence": result}},
            )

        return {**result, "_chat_result": chat_result}


# ─────────────────────────────────────────────────────────────────────────────
# Reusability Agent
# ─────────────────────────────────────────────────────────────────────────────

_REUSE_SYSTEM = """You are MERGENT's Reusability Calculator.
Given a fork plan and clone intelligence analysis, calculate the true cost and effort of the fork.
Hourly rate assumption: $75/hr.
Return ONLY JSON:
{
  "effort_score": 0-100 (higher = more effort required),
  "total_hours": integer,
  "cost_estimate_usd": integer,
  "vs_build_from_scratch_hours": integer,
  "hours_saved": integer,
  "cost_savings_usd": integer,
  "verdict": "worth_forking" | "consider_building" | "build_fresh",
  "verdict_reasoning": "one sentence",
  "timeline_weeks": integer
}
JSON only."""

HOURLY_RATE = 75


class ReusabilityAgent(BaseAgent):
    agent_name = "ReusabilityAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        fork_plan = input.get("fork_plan", {}) or {}
        clone_intelligence = input.get("clone_intelligence", {}) or {}

        combined = {
            "fork_plan": {
                "total_estimated_hours": fork_plan.get("total_estimated_hours", 0),
                "reuse_percentage": fork_plan.get("reuse_percentage", 50),
                "complexity": fork_plan.get("complexity", "moderate"),
                "features_to_add_count": len(fork_plan.get("features_to_add", []) or []),
                "features_to_modify_count": len(fork_plan.get("features_to_modify", []) or []),
            },
            "clone_intelligence": {
                "reuse_score": clone_intelligence.get("reuse_score", 50),
                "recommended_base": clone_intelligence.get("recommended_base", "needs_significant_changes"),
                "estimated_reuse_hours_saved": clone_intelligence.get("estimated_reuse_hours_saved", 0),
                "rebuild_required_count": len(clone_intelligence.get("rebuild_required", []) or []),
            },
            "hourly_rate_usd": HOURLY_RATE,
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _REUSE_SYSTEM},
                {"role": "user", "content": f"Calculate reusability:\n{combined}\n\nReturn JSON now."},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=500,
        )

        # Ensure cost_estimate_usd is computed
        if not result.get("cost_estimate_usd") and result.get("total_hours"):
            result["cost_estimate_usd"] = result["total_hours"] * HOURLY_RATE

        # Update fork request
        fork_request_id = input.get("fork_request_id")
        if fork_request_id:
            db = get_db()
            await db.fork_requests.update_one(
                {"_id": fork_request_id},
                {"$set": {"reusability_result": result}},
            )

        return {**result, "_chat_result": chat_result}


# Module-level shim functions for direct invocation
async def run_forking(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ForkingAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_similarity(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await SimilarityAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_clone_intelligence(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await CloneIntelligenceAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_reusability(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ReusabilityAgent().execute(ctx, run_id=ctx.get("run_id"))
