"""Executive Layer Agents — the cognitive OS of MERGENT.

SupervisorAgent       — owns the top-level goal, delegates, monitors, replans
PlannerAgent          — translates goals into ordered execution plans
ExecutionOptimizerAgent — monitors cost/tokens, routes tasks to right models

These three form the reasoning loop:
  Supervisor → delegates → Planner → creates plan → agents execute
  → ExecutionOptimizer monitors cost → Reflection challenges output
  → Supervisor decides proceed or replan
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from db import get_db
from services.ai_provider import get_ai_provider

# ─────────────────────────────────────────────────────────────────────────────
# Supervisor Agent
# ─────────────────────────────────────────────────────────────────────────────

_SUPERVISOR_SYSTEM = """You are MERGENT's Supervisor Agent — the CEO of every buyer session.
You own the top-level goal: find the best software solution for this buyer.

Given the current session state, decide:
1. Is the goal achieved? (good results, buyer has what they need)
2. Does the plan need adjustment?
3. Which layer should execute next?

Return ONLY JSON:
{
  "goal_achieved": true | false,
  "goal_confidence": "high" | "medium" | "low",
  "current_status": "one sentence on where we are",
  "next_action": "deliver_results" | "rerun_discovery" | "expand_search" | "escalate_to_human",
  "delegation_target": "discovery" | "trust" | "commercial" | "forking" | null,
  "reasoning": "one sentence",
  "session_health": "good" | "degraded" | "failed"
}
JSON only."""


class SupervisorAgent(BaseAgent):
    agent_name = "SupervisorAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        session_id = input.get("session_id") or input.get("run_id")
        ranked = input.get("ranked", []) or []
        parsed = input.get("parsed_requirement", {}) or {}
        reflection = input.get("reflection_result", {}) or {}
        attempt = input.get("attempt", 0)

        top_score = ranked[0].get("score", 0) if ranked else 0
        result_count = len(ranked)

        state_summary = {
            "session_id": session_id,
            "attempt": attempt,
            "result_count": result_count,
            "top_score": top_score,
            "reflection_approved": reflection.get("reflection_approved", True),
            "reflection_severity": reflection.get("reflection_severity", "none"),
            "replan_recommended": reflection.get("replan_recommended", False),
            "requirement_category": parsed.get("category", ""),
            "missing_critical_features": reflection.get("missing_critical_features", []),
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SUPERVISOR_SYSTEM},
                {"role": "user", "content": f"Session state:\n{state_summary}\n\nReturn supervision decision JSON now."},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=400,
        )

        # Log supervision decision
        if session_id:
            await db.supervision_log.insert_one({
                "session_id": session_id,
                "attempt": attempt,
                "decision": result,
                "state_snapshot": state_summary,
                "created_at": datetime.now(timezone.utc),
            })

        return {
            "supervisor_decision": result,
            "goal_achieved": result.get("goal_achieved", True),
            "next_action": result.get("next_action", "deliver_results"),
            "delegation_target": result.get("delegation_target"),
            "_chat_result": chat_result,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Planner Agent
# ─────────────────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """You are MERGENT's Planner Agent.
Given a buyer's requirement, create a concrete execution plan.

Available agent steps (in order of dependency):
  intake → parser → embedding → search → compression → ranking
  → match_intelligence → reflection → acquisition_advisor

Additional parallel steps (run after ranking):
  trust_audit, roi_calculation, commercialization, architecture_explanation

Return ONLY JSON:
{
  "plan_id": "unique short id e.g. plan_001",
  "steps": [
    {
      "step": "agent_name",
      "required": true | false,
      "depends_on": ["step_name"] or [],
      "parallel_with": ["step_name"] or [],
      "skip_condition": "condition to skip this step or null"
    }
  ],
  "estimated_llm_calls": integer,
  "estimated_tokens": integer,
  "plan_reasoning": "one sentence on the approach"
}
JSON only."""


class PlannerAgent(BaseAgent):
    agent_name = "PlannerAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        requirement_text = input.get("requirement_text", "")
        context = input.get("context", {}) or {}
        replan_reason = input.get("replan_reason")

        plan_context = {
            "requirement": requirement_text[:300],
            "replan_reason": replan_reason,
            "expand_search": context.get("expand_search", False),
            "surface_alternatives": context.get("surface_alternatives", False),
            "attempt": context.get("attempt", 0),
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": f"Create execution plan for:\n{plan_context}\n\nReturn plan JSON now."},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=800,
        )

        return {
            "execution_plan": result,
            "plan_id": result.get("plan_id", "plan_default"),
            "estimated_llm_calls": result.get("estimated_llm_calls", 6),
            "_chat_result": chat_result,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Execution Optimizer Agent
# ─────────────────────────────────────────────────────────────────────────────

# Cost per 1k tokens by model (approximate USD)
COST_TABLE: Dict[str, float] = {
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.000165,
    "claude-3-5-sonnet": 0.003,
    "claude-3-haiku": 0.00025,
    "gemini-1.5-flash": 0.000075,
    "gemini-1.5-pro": 0.0035,
}

# Which agents are cheap enough for lightweight models
LIGHTWEIGHT_AGENTS = {
    "IntakeAgent",
    "MarketIntelligenceAgent",
    "ReputationAgent",
    "TicketTriageAgent",
    "EscalationAgent",
}

# Which agents need the best model
PREMIUM_AGENTS = {
    "RankingAgent",
    "ReflectionAgent",
    "AcquisitionAdvisorAgent",
    "AgenticOrchestrator",
    "SupervisorAgent",
}


class ExecutionOptimizerAgent(BaseAgent):
    agent_name = "ExecutionOptimizerAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        """Analyze usage and produce routing recommendations."""
        db = get_db()
        run_id = input.get("run_id")
        action = input.get("action", "analyze")

        if action == "route":
            return self._get_model_routing(input.get("agent_name", ""))

        if action == "analyze" and run_id:
            return await self._analyze_run_cost(db, run_id)

        # Default: return routing table
        return self._get_full_routing_table()

    def _get_model_routing(self, agent_name: str) -> Dict[str, Any]:
        """Return recommended model for a given agent."""
        if agent_name in PREMIUM_AGENTS:
            return {
                "agent_name": agent_name,
                "recommended_model": "gpt-4o",
                "reason": "High-stakes decision — use best model",
                "fallback_model": "claude-3-5-sonnet",
            }
        elif agent_name in LIGHTWEIGHT_AGENTS:
            return {
                "agent_name": agent_name,
                "recommended_model": "gpt-4o-mini",
                "reason": "Simple aggregation — lightweight model sufficient",
                "fallback_model": "gemini-1.5-flash",
            }
        else:
            return {
                "agent_name": agent_name,
                "recommended_model": "gpt-4o-mini",
                "reason": "Standard agent — balanced model",
                "fallback_model": "claude-3-haiku",
            }

    async def _analyze_run_cost(self, db: Any, run_id: str) -> Dict[str, Any]:
        """Analyze actual cost of a completed run."""
        logs = [d async for d in db.ai_usage_logs.find({"run_id": run_id})]

        total_tokens = sum(
            (d.get("tokens_in", 0) or 0) + (d.get("tokens_out", 0) or 0)
            for d in logs
        )
        total_cost = sum(d.get("cost_usd", 0) or 0 for d in logs)
        calls_by_agent: Dict[str, int] = {}
        cost_by_agent: Dict[str, float] = {}

        for log in logs:
            agent = log.get("agent_name", "unknown")
            calls_by_agent[agent] = calls_by_agent.get(agent, 0) + 1
            cost_by_agent[agent] = cost_by_agent.get(agent, 0.0) + (log.get("cost_usd", 0) or 0)

        # Find most expensive agent
        most_expensive = max(cost_by_agent, key=cost_by_agent.get) if cost_by_agent else None

        # Optimization suggestions
        suggestions: List[str] = []
        for agent, cost in cost_by_agent.items():
            if agent not in PREMIUM_AGENTS and cost > 0.002:
                suggestions.append(
                    f"{agent} cost ${cost:.4f} — consider routing to gpt-4o-mini"
                )
        if total_tokens > 10000:
            suggestions.append("High token usage — consider enabling ContextCompressionAgent")

        return {
            "run_id": run_id,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "total_llm_calls": len(logs),
            "calls_by_agent": calls_by_agent,
            "cost_by_agent": {k: round(v, 6) for k, v in cost_by_agent.items()},
            "most_expensive_agent": most_expensive,
            "optimization_suggestions": suggestions,
        }

    def _get_full_routing_table(self) -> Dict[str, Any]:
        return {
            "premium_agents": list(PREMIUM_AGENTS),
            "lightweight_agents": list(LIGHTWEIGHT_AGENTS),
            "routing_table": {
                agent: self._get_model_routing(agent)
                for agent in list(PREMIUM_AGENTS) + list(LIGHTWEIGHT_AGENTS)
            },
        }


# Shim functions
async def run_supervisor(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await SupervisorAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_planner(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await PlannerAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_execution_optimizer(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ExecutionOptimizerAgent().execute(ctx, run_id=ctx.get("run_id"))
