"""Deployment Layer Agents.

DeploymentSupervisorAgent — manages 7-step deployment state machine
HealthMonitorAgent        — tracks uptime via Celery beat (every 5 min)
IncidentAgent             — classifies and handles deployment failures

Deployment steps (simulated state machine in DB — no real Docker yet):
  1. initialize  2. configure  3. migrate_db
  4. setup_env   5. deploy     6. health_check  7. live
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from agents.base import BaseAgent
from db import get_db

DEPLOYMENT_STEPS: List[str] = [
    "initialize",
    "configure",
    "migrate_db",
    "setup_env",
    "deploy",
    "health_check",
    "live",
]

STEP_MESSAGES: Dict[str, str] = {
    "initialize":    "Initializing deployment environment...",
    "configure":     "Building configuration...",
    "migrate_db":    "Running database migrations...",
    "setup_env":     "Injecting environment variables...",
    "deploy":        "Deploying application...",
    "health_check":  "Running health checks...",
    "live":          "Switching production traffic...",
}

STEP_DURATION_SECONDS: Dict[str, int] = {
    "initialize": 2, "configure": 3, "migrate_db": 4,
    "setup_env": 2, "deploy": 5, "health_check": 3, "live": 1,
}


# ─────────────────────────────────────────────────────────────────────────────
# Deployment Supervisor Agent
# ─────────────────────────────────────────────────────────────────────────────

class DeploymentSupervisorAgent(BaseAgent):
    agent_name = "DeploymentSupervisorAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        action = input.get("action", "create")

        if action == "create":
            return await self._create_deployment(input)
        elif action == "advance":
            return await self._advance_step(input)
        elif action == "rollback":
            return await self._rollback(input)
        elif action == "fail":
            return await self._fail_deployment(input)
        return {"error": f"unknown_action: {action}"}

    async def _create_deployment(self, input: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        solution_id = input.get("solution_id")
        buyer_id = input.get("buyer_id")

        steps_initial = {
            step: {
                "status": "pending",
                "message": STEP_MESSAGES[step],
                "started_at": None,
                "completed_at": None,
                "logs": "",
            }
            for step in DEPLOYMENT_STEPS
        }

        deployment = {
            "solution_id": solution_id,
            "buyer_id": buyer_id,
            "status": "initializing",
            "current_step": "initialize",
            "steps": steps_initial,
            "version": 1,
            "uptime_percent": 0.0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await db.deployments.insert_one(deployment)
        deployment_id = str(result.inserted_id)

        # Notify buyer
        if buyer_id:
            await db.notifications.insert_one({
                "user_id": buyer_id,
                "type": "deployment_started",
                "message": "Your deployment has started.",
                "link": f"/deployments/{deployment_id}",
                "read": False,
                "created_at": datetime.now(timezone.utc),
            })

        return {"deployment_id": deployment_id, "status": "initializing"}

    async def _advance_step(self, input: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        deployment_id = input.get("deployment_id")
        step = input.get("step")
        logs = input.get("logs", "")

        if not deployment_id or not step:
            return {"error": "deployment_id and step required"}

        now = datetime.now(timezone.utc)
        step_idx = DEPLOYMENT_STEPS.index(step) if step in DEPLOYMENT_STEPS else -1
        is_last = step == DEPLOYMENT_STEPS[-1]
        next_step = DEPLOYMENT_STEPS[step_idx + 1] if not is_last and step_idx >= 0 else None

        update: Dict[str, Any] = {
            f"steps.{step}.status": "done",
            f"steps.{step}.completed_at": now,
            f"steps.{step}.logs": logs,
            "updated_at": now,
        }

        if is_last:
            update["status"] = "live"
            update["went_live_at"] = now
            update["uptime_percent"] = 100.0
        elif next_step:
            update["current_step"] = next_step
            update["status"] = "running"
            update[f"steps.{next_step}.status"] = "running"
            update[f"steps.{next_step}.started_at"] = now

        await db.deployments.update_one({"_id": deployment_id}, {"$set": update})
        return {"deployment_id": deployment_id, "step_completed": step, "next_step": next_step}

    async def _rollback(self, input: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        deployment_id = input.get("deployment_id")
        reason = input.get("reason", "Manual rollback")

        await db.deployments.update_one(
            {"_id": deployment_id},
            {"$set": {
                "status": "rolled_back",
                "rollback_reason": reason,
                "rolled_back_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        deployment = await db.deployments.find_one({"_id": deployment_id}) or {}
        buyer_id = deployment.get("buyer_id")
        if buyer_id:
            await db.notifications.insert_one({
                "user_id": buyer_id,
                "type": "deployment_rollback",
                "message": f"Deployment rolled back: {reason}",
                "link": f"/deployments/{deployment_id}",
                "read": False,
                "created_at": datetime.now(timezone.utc),
            })

        return {"deployment_id": deployment_id, "status": "rolled_back"}

    async def _fail_deployment(self, input: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        deployment_id = input.get("deployment_id")
        failed_step = input.get("failed_step")
        error_msg = input.get("error", "Unknown error")

        update: Dict[str, Any] = {
            "status": "failed",
            "failed_at": datetime.now(timezone.utc),
            "failure_reason": error_msg,
            "updated_at": datetime.now(timezone.utc),
        }
        if failed_step:
            update[f"steps.{failed_step}.status"] = "failed"
            update[f"steps.{failed_step}.logs"] = error_msg

        await db.deployments.update_one({"_id": deployment_id}, {"$set": update})
        return {"deployment_id": deployment_id, "status": "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# Health Monitor Agent (Celery beat — runs every 5 min)
# ─────────────────────────────────────────────────────────────────────────────

class HealthMonitorAgent(BaseAgent):
    agent_name = "HealthMonitorAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        deployment_id: Optional[str] = input.get("deployment_id")

        # If specific deployment, check just that one
        if deployment_id:
            deployment = await db.deployments.find_one({"_id": deployment_id}) or {}
            return await self._check_single(deployment)

        # Otherwise check all live deployments
        cursor = db.deployments.find({"status": "live"}, {"_id": 1, "solution_id": 1, "buyer_id": 1})
        deployments = [d async for d in cursor]

        results = []
        for dep in deployments:
            result = await self._check_single(dep)
            results.append(result)

        return {"checked": len(results), "results": results}

    async def _check_single(self, deployment: Dict[str, Any]) -> Dict[str, Any]:
        db = get_db()
        deployment_id = deployment.get("_id")
        solution_id = deployment.get("solution_id")

        # Get demo URL from solution
        solution = await db.solutions.find_one({"_id": solution_id}, {"demo_url": 1}) or {}
        demo_url = solution.get("demo_url")

        status = "up"
        response_time_ms = 0

        if demo_url:
            try:
                import time
                t0 = time.perf_counter()
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(demo_url)
                    response_time_ms = int((time.perf_counter() - t0) * 1000)
                    status = "up" if resp.status_code < 500 else "down"
            except Exception:
                status = "down"

        # Record health check
        await db.health_checks.insert_one({
            "deployment_id": deployment_id,
            "status": status,
            "response_time_ms": response_time_ms,
            "checked_at": datetime.now(timezone.utc),
        })

        # Calculate uptime % over last 30 days
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=30)
        total_checks = await db.health_checks.count_documents({
            "deployment_id": deployment_id,
            "checked_at": {"$gte": since},
        })
        up_checks = await db.health_checks.count_documents({
            "deployment_id": deployment_id,
            "status": "up",
            "checked_at": {"$gte": since},
        })
        uptime_pct = round((up_checks / total_checks * 100) if total_checks > 0 else 100.0, 2)

        await db.deployments.update_one(
            {"_id": deployment_id},
            {"$set": {
                "uptime_percent": uptime_pct,
                "last_health_check": datetime.now(timezone.utc),
                "last_response_time_ms": response_time_ms,
            }},
        )

        # Also update solution uptime
        if solution_id:
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {"uptime_pct": uptime_pct}},
            )

        # Check for consecutive failures
        recent = [d async for d in db.health_checks.find(
            {"deployment_id": deployment_id},
        ).sort("checked_at", -1).limit(3)]
        consecutive_failures = sum(1 for h in recent if h.get("status") == "down")

        if consecutive_failures >= 3:
            # Trigger incident
            incident_agent = IncidentAgent(provider=self.provider)
            await incident_agent.execute({
                "deployment_id": deployment_id,
                "incident_type": "consecutive_health_failures",
                "details": {
                    "consecutive_failures": consecutive_failures,
                    "last_response_time_ms": response_time_ms,
                },
            })

        return {
            "deployment_id": str(deployment_id),
            "status": status,
            "uptime_pct": uptime_pct,
            "response_time_ms": response_time_ms,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Incident Agent
# ─────────────────────────────────────────────────────────────────────────────

_INCIDENT_SYSTEM = """You are MERGENT's Incident Classifier.
Given a deployment incident, classify it and recommend action.
Return ONLY JSON:
{
  "severity": "low" | "medium" | "high",
  "classification": "transient_failure" | "repeated_failure" | "total_outage" | "degraded_performance",
  "suggested_action": "monitor" | "notify_builder" | "auto_rollback" | "manual_intervention",
  "notify_buyer": true | false,
  "auto_rollback": true | false,
  "message_to_buyer": "one sentence explanation if notify_buyer=true",
  "message_to_builder": "one sentence explanation"
}
JSON only."""


class IncidentAgent(BaseAgent):
    agent_name = "IncidentAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        deployment_id = input.get("deployment_id")
        incident_type = input.get("incident_type", "unknown")
        details = input.get("details", {}) or {}

        deployment = await db.deployments.find_one({"_id": deployment_id}) or {}

        incident_context = {
            "incident_type": incident_type,
            "details": details,
            "deployment_status": deployment.get("status"),
            "uptime_percent": deployment.get("uptime_percent", 100),
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _INCIDENT_SYSTEM},
                {"role": "user", "content": f"Incident:\n{incident_context}\n\nReturn classification JSON now."},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=400,
        )

        severity = result.get("severity", "medium")

        # Save incident record
        await db.incidents.insert_one({
            "deployment_id": deployment_id,
            "type": incident_type,
            "severity": severity,
            "classification": result.get("classification", ""),
            "details_json": details,
            "suggested_action": result.get("suggested_action", "monitor"),
            "auto_rollback": result.get("auto_rollback", False),
            "resolved": False,
            "created_at": datetime.now(timezone.utc),
        })

        buyer_id = deployment.get("buyer_id")
        solution_id = deployment.get("solution_id")

        # Notify buyer if needed
        if result.get("notify_buyer") and buyer_id:
            await db.notifications.insert_one({
                "user_id": buyer_id,
                "type": "deployment_incident",
                "message": result.get("message_to_buyer", "There is an issue with your deployment."),
                "link": f"/deployments/{deployment_id}",
                "read": False,
                "created_at": datetime.now(timezone.utc),
            })

        # Notify builder
        if solution_id:
            solution = await db.solutions.find_one({"_id": solution_id}, {"builder_id": 1}) or {}
            builder_id = solution.get("builder_id")
            if builder_id:
                await db.notifications.insert_one({
                    "user_id": builder_id,
                    "type": "deployment_incident",
                    "message": result.get("message_to_builder", "A deployment of your solution has an incident."),
                    "link": f"/deployments/{deployment_id}",
                    "read": False,
                    "created_at": datetime.now(timezone.utc),
                })

        # Auto-rollback if recommended
        if result.get("auto_rollback") and deployment_id:
            supervisor = DeploymentSupervisorAgent(provider=self.provider)
            await supervisor.execute({
                "action": "rollback",
                "deployment_id": deployment_id,
                "reason": f"Auto-rollback triggered by IncidentAgent: {incident_type}",
            })

        return {**result, "incident_recorded": True, "_chat_result": chat_result}


# Shim functions
async def run_supervisor(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await DeploymentSupervisorAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_health_monitor(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await HealthMonitorAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_incident(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await IncidentAgent().execute(ctx, run_id=ctx.get("run_id"))
