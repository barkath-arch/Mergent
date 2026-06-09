"""MatchIntelligenceAgent — per-candidate fit scorer with missing_features analysis.

Runs AFTER RankingAgent. Enriches each ranked result with:
- missing_features: what the buyer asked for that this solution lacks
- fit_analysis: why the score is what it is in plain English
- deal_breakers: critical gaps that should disqualify the solution

This is distinct from RankingAgent which does bulk relative scoring.
MatchIntelligenceAgent does deep per-candidate analysis.
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base import BaseAgent

_SYSTEM_PROMPT = """You are MERGENT's Match Intelligence Agent.
Perform a deep fit analysis between one buyer requirement and one candidate solution.

Be specific and honest. Reference actual fields.

Return ONLY JSON:
{
  "fit_score": 0-100,
  "fit_analysis": "2 sentences explaining why this solution does or doesn't fit",
  "missing_features": ["feature buyer asked for that solution lacks"],
  "present_features": ["feature buyer asked for that solution has"],
  "deal_breakers": ["critical gaps that should disqualify — empty if none"],
  "strengths": ["top 2-3 strengths relevant to this buyer"],
  "confidence": "high" | "medium" | "low",
  "recommendation": "strong_match" | "good_match" | "partial_match" | "poor_match"
}
JSON only."""


class MatchIntelligenceAgent(BaseAgent):
    agent_name = "MatchIntelligenceAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        ranked: List[Dict[str, Any]] = input.get("ranked", []) or []
        candidates: List[Dict[str, Any]] = input.get("candidates", []) or []
        parsed = input.get("parsed_requirement", {}) or {}

        if not ranked or not candidates:
            return {"enriched_ranked": ranked, "match_intelligence_skipped": True}

        # Build lookup by id
        candidates_by_id = {str(c.get("_id")): c for c in candidates}

        enriched: List[Dict[str, Any]] = []
        # Only deep-analyze top 5 to control LLM cost
        for rank_entry in ranked[:5]:
            solution_id = str(rank_entry.get("solutionId") or rank_entry.get("solution_id", ""))
            solution = candidates_by_id.get(solution_id, {})

            if not solution:
                enriched.append(rank_entry)
                continue

            solution_summary = {
                "title": solution.get("title", ""),
                "description": solution.get("description", ""),
                "category": solution.get("category", ""),
                "tech_stack": solution.get("tech_stack", []),
                "tags": solution.get("tags", []),
                "deployment_maturity": solution.get("deployment_maturity", ""),
            }

            requirement_summary = {
                "required_features": parsed.get("required_features", []),
                "category": parsed.get("category", ""),
                "business_domain": parsed.get("business_domain", ""),
                "tech_preferences": parsed.get("tech_preferences", []),
                "compliance_requirements": parsed.get("compliance_requirements", []),
                "deployment_complexity": parsed.get("deployment_complexity", ""),
            }

            user_msg = (
                f"Buyer requirement:\n{requirement_summary}\n\n"
                f"Candidate solution:\n{solution_summary}\n\n"
                "Return deep fit analysis JSON now."
            )

            result, _ = await self._llm(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                json_mode=True,
                max_tokens=600,
            )

            # Merge into rank entry
            enriched.append({
                **rank_entry,
                "missing_features": result.get("missing_features", []),
                "present_features": result.get("present_features", []),
                "deal_breakers": result.get("deal_breakers", []),
                "strengths": result.get("strengths", []),
                "fit_analysis": result.get("fit_analysis", ""),
                "match_recommendation": result.get("recommendation", "partial_match"),
                "match_intelligence_confidence": result.get("confidence", "medium"),
            })

        # Append remaining unanalyzed results as-is
        for rank_entry in ranked[5:]:
            enriched.append(rank_entry)

        return {
            "ranked": enriched,
            "enriched_ranked": enriched,
            "match_intelligence_applied": True,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await MatchIntelligenceAgent().execute(ctx, run_id=ctx.get("run_id"))
