"""AgenticOrchestrator — true agentic loop on top of the pipeline.

This is the upgrade from a linear pipeline to a genuine agent loop:

  while goal_not_met and attempts < MAX_ATTEMPTS:
      plan  = PlannerStep.decide(state)
      result = execute_step(plan)
      reflection = ReflectionAgent.evaluate(result)
      if reflection.approved:
          advance_state()
      else:
          replan(reflection.concern)

The existing OrchestratorService (linear pipeline) is preserved.
This class wraps it with replanning capability.

Used via: POST /api/match/agentic  (new endpoint)
Original: POST /api/match          (linear pipeline — unchanged)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.discovery.reflection import ReflectionAgent
from db import get_db
from services.ai_provider import get_ai_provider
from services.logging_config import get_logger

logger = get_logger(__name__)

MAX_REPLAN_ATTEMPTS = 3
MIN_ACCEPTABLE_SCORE = 60  # Replan if top score below this


_PLANNER_SYSTEM = """You are MERGENT's Planner Agent.
Given a buyer's requirement and current match state, decide the next step.

Available actions:
- "proceed": results are good enough, deliver to buyer
- "expand_search": broaden the search (relax category, add similar categories)
- "refine_requirement": re-parse requirement with different emphasis
- "lower_threshold": accept lower match scores
- "surface_alternatives": explicitly look for fork candidates instead of exact matches

Return ONLY JSON:
{
  "action": "proceed" | "expand_search" | "refine_requirement" | "lower_threshold" | "surface_alternatives",
  "reasoning": "one sentence",
  "modified_search_hint": "hint for the search agent if action != proceed, else null"
}
JSON only."""


class AgenticOrchestrator:
    """Wraps the linear pipeline with a true goal-driven replanning loop."""

    def __init__(self) -> None:
        self.provider = get_ai_provider()
        self.reflection_agent = ReflectionAgent(provider=self.provider)

    async def run_agentic_match(
        self,
        requirement_text: str,
        buyer_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full agentic match with replanning loop."""
        db = get_db()
        now = datetime.now(timezone.utc)

        # Create agentic run record
        agentic_run = {
            "run_id": run_id,
            "buyer_id": buyer_id,
            "requirement_text": requirement_text,
            "status": "running",
            "attempts": 0,
            "plan_history": [],
            "reflection_history": [],
            "final_result": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.agentic_runs.insert_one(agentic_run)

        state: Dict[str, Any] = {
            "requirement_text": requirement_text,
            "buyer_id": buyer_id,
            "run_id": run_id,
            "attempt": 0,
            "search_hint": None,
            "replan_reason": None,
        }

        final_result: Dict[str, Any] = {}
        plan_history: List[Dict[str, Any]] = []
        reflection_history: List[Dict[str, Any]] = []

        for attempt in range(MAX_REPLAN_ATTEMPTS):
            state["attempt"] = attempt
            logger.info("agentic_loop_attempt", extra={"attempt": attempt, "run_id": run_id})

            # Run the linear pipeline (existing OrchestratorService logic)
            pipeline_result = await self._run_pipeline(state)

            ranked = pipeline_result.get("ranked", [])
            top_score = ranked[0].get("score", 0) if ranked else 0

            # Run reflection on top result
            reflection_input = {
                **state,
                "ranked": ranked,
                "candidates": pipeline_result.get("candidates", []),
                "parsed_requirement": pipeline_result.get("parsed_requirement", {}),
            }
            reflection_result = await self.reflection_agent.execute(
                reflection_input, run_id=run_id
            )
            reflection_history.append({
                "attempt": attempt,
                "approved": reflection_result.get("reflection_approved"),
                "concern": reflection_result.get("reflection_concern"),
                "severity": reflection_result.get("reflection_severity"),
            })

            # Decide next action
            plan = await self._plan(
                state=state,
                ranked=ranked,
                top_score=top_score,
                reflection=reflection_result,
                attempt=attempt,
            )
            plan_history.append({"attempt": attempt, **plan})

            if plan["action"] == "proceed":
                # Merge reflection adjustments into result
                final_result = {
                    **pipeline_result,
                    "ranked": reflection_result.get("ranked", ranked),
                    "reflection": reflection_result,
                    "agentic_attempts": attempt + 1,
                    "plan_history": plan_history,
                }
                break

            # Modify state for next attempt based on plan
            state["replan_reason"] = reflection_result.get("reflection_concern")
            state["search_hint"] = plan.get("modified_search_hint")

            if plan["action"] == "expand_search":
                state["expand_search"] = True
            elif plan["action"] == "refine_requirement":
                state["refine_requirement"] = True
                state["requirement_text"] = (
                    requirement_text + f"\n\nNote: {plan.get('modified_search_hint', '')}"
                )
            elif plan["action"] == "lower_threshold":
                state["min_score_override"] = MIN_ACCEPTABLE_SCORE - 20
            elif plan["action"] == "surface_alternatives":
                state["surface_alternatives"] = True

            # Update DB with current attempt
            await db.agentic_runs.update_one(
                {"run_id": run_id},
                {"$set": {
                    "attempts": attempt + 1,
                    "plan_history": plan_history,
                    "reflection_history": reflection_history,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )

        else:
            # Max attempts reached — return best result we have
            final_result = {
                **pipeline_result,
                "reflection": reflection_result,
                "agentic_attempts": MAX_REPLAN_ATTEMPTS,
                "plan_history": plan_history,
                "max_attempts_reached": True,
            }

        # Finalize agentic run record
        await db.agentic_runs.update_one(
            {"run_id": run_id},
            {"$set": {
                "status": "completed",
                "final_result": {
                    "result_count": len(final_result.get("ranked", [])),
                    "top_score": final_result.get("ranked", [{}])[0].get("score", 0) if final_result.get("ranked") else 0,
                    "attempts": final_result.get("agentic_attempts", 1),
                },
                "plan_history": plan_history,
                "reflection_history": reflection_history,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        return final_result

    async def _plan(
        self,
        state: Dict[str, Any],
        ranked: List[Dict[str, Any]],
        top_score: float,
        reflection: Dict[str, Any],
        attempt: int,
    ) -> Dict[str, Any]:
        """Planner decides: proceed or which replan strategy."""

        # Fast-path: if reflection approved and score is good, proceed
        if reflection.get("reflection_approved") and top_score >= MIN_ACCEPTABLE_SCORE:
            return {"action": "proceed", "reasoning": "Reflection approved, score sufficient."}

        # Last attempt: proceed regardless
        if attempt >= MAX_REPLAN_ATTEMPTS - 1:
            return {"action": "proceed", "reasoning": "Max attempts reached — delivering best result."}

        # Ask LLM planner
        planner_input = {
            "requirement": state.get("requirement_text", "")[:300],
            "attempt": attempt,
            "top_score": top_score,
            "result_count": len(ranked),
            "reflection_concern": reflection.get("reflection_concern"),
            "reflection_severity": reflection.get("reflection_severity"),
            "missing_features": reflection.get("missing_critical_features", []),
            "replan_recommended": reflection.get("replan_recommended", False),
        }

        provider = self.provider
        parsed, _ = await provider.chat_json(
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": f"Current state:\n{planner_input}\n\nDecide next action JSON now."},
            ],
            temperature=0.2,
            max_tokens=300,
            agent_name="PlannerAgent",
        )
        return parsed

    async def _run_pipeline(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run the linear pipeline (delegates to existing orchestrator logic)."""
        # Import here to avoid circular imports
        from services.orchestrator import run_pipeline_steps
        return await run_pipeline_steps(state)


# Singleton
_agentic_orchestrator: Optional[AgenticOrchestrator] = None


def get_agentic_orchestrator() -> AgenticOrchestrator:
    global _agentic_orchestrator
    if _agentic_orchestrator is None:
        _agentic_orchestrator = AgenticOrchestrator()
    return _agentic_orchestrator
