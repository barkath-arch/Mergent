"""ReflectionAgent — adversarial reviewer that challenges the top-ranked result.

Part of the agentic loop: after RankingAgent produces results, ReflectionAgent
acts as an internal critic. If it rejects the top result, the OrchestratorService
can replan (expand search, relax filters, or surface the next candidate).

This is the first step toward a true agentic loop — the output of this agent
feeds back into the Supervisor's replanning logic.
"""
from __future__ import annotations

from typing import Any, Dict

from agents.base import BaseAgent

_SYSTEM_PROMPT = """You are MERGENT's Reflection Agent — an adversarial internal reviewer.
Your job is to challenge the top-ranked software solution BEFORE it is shown to the buyer.
Be honest, skeptical, and specific. Do not be polite about mismatches.

Given a buyer's parsed requirement and the top-ranked solution, evaluate:
1. Does the solution genuinely solve the core problem?
2. Are there critical missing features the buyer explicitly asked for?
3. Is the confidence score warranted or inflated?
4. Are there deployment/compliance/tech-stack concerns the buyer should know?

Return ONLY a JSON object:
{
  "approved": true | false,
  "concern": "string describing the main concern, or null if approved cleanly",
  "severity": "none" | "minor" | "major" | "critical",
  "confidence_adjustment": -20 to +10 (integer — negative if concern reduces confidence),
  "alternative_suggestion": "string suggesting what to look for instead, or null",
  "missing_critical_features": ["list of features buyer asked for that solution lacks"],
  "replan_recommended": true | false
}

Rules:
- If approved=true and severity=none: the match is genuinely good.
- If approved=false: replan_recommended should almost always be true.
- confidence_adjustment must reflect severity: critical=-20, major=-10, minor=-5, none=0 or positive.
- Be specific — reference actual fields from the requirement and solution.
JSON only. No prose.
"""


class ReflectionAgent(BaseAgent):
    agent_name = "ReflectionAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        ranked: list = input.get("ranked", []) or []
        parsed = input.get("parsed_requirement", {}) or {}
        candidates: list = input.get("candidates", []) or []

        if not ranked or not candidates:
            return {
                "reflection_approved": True,
                "reflection_concern": None,
                "reflection_severity": "none",
                "confidence_adjustment": 0,
                "alternative_suggestion": None,
                "missing_critical_features": [],
                "replan_recommended": False,
                "reflection_skipped": True,
            }

        top = ranked[0]
        top_id = top.get("solutionId") or top.get("solution_id")
        top_solution = next((c for c in candidates if str(c.get("_id")) == str(top_id)), None)

        if not top_solution:
            return {
                "reflection_approved": True,
                "reflection_concern": "Top solution not found in candidates — skipping reflection.",
                "reflection_severity": "minor",
                "confidence_adjustment": -5,
                "alternative_suggestion": None,
                "missing_critical_features": [],
                "replan_recommended": False,
                "reflection_skipped": True,
            }

        solution_summary = {
            "id": top_solution.get("_id"),
            "title": top_solution.get("title", ""),
            "description": top_solution.get("description", ""),
            "category": top_solution.get("category", ""),
            "tech_stack": top_solution.get("tech_stack", []),
            "tags": top_solution.get("tags", []),
            "deployment_maturity": top_solution.get("deployment_maturity", ""),
            "ranking_score": top.get("score", 0),
            "ranking_explanation": top.get("explanation", ""),
            "ranking_confidence": top.get("confidence", "medium"),
        }

        user_msg = (
            f"Buyer requirement:\n{parsed}\n\n"
            f"Top-ranked solution:\n{solution_summary}\n\n"
            "Challenge this match. Return the reflection JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=800,
        )

        approved = bool(result.get("approved", True))
        severity = result.get("severity", "none")
        adjustment = int(result.get("confidence_adjustment", 0))
        adjustment = max(-20, min(10, adjustment))

        # Apply confidence adjustment to ranked results
        adjusted_ranked = list(ranked)
        if adjusted_ranked and adjustment != 0:
            adjusted_ranked[0] = {
                **adjusted_ranked[0],
                "score": max(0, min(100, float(adjusted_ranked[0].get("score", 0)) + adjustment)),
                "reflection_adjusted": True,
            }

        return {
            "reflection_approved": approved,
            "reflection_concern": result.get("concern"),
            "reflection_severity": severity,
            "confidence_adjustment": adjustment,
            "alternative_suggestion": result.get("alternative_suggestion"),
            "missing_critical_features": result.get("missing_critical_features", []),
            "replan_recommended": bool(result.get("replan_recommended", False)),
            "ranked": adjusted_ranked,
            "reflection_skipped": False,
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ReflectionAgent().execute(ctx, run_id=ctx.get("run_id"))
