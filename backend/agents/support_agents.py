"""Support Layer Agents.

TicketTriageAgent      — classifies support tickets, auto-resolves simple ones
EscalationAgent        — routes unresolved tickets after 48h or urgency=high
CustomerSuccessAgent   — re-engages inactive buyers (Celery beat daily)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from agents.base import BaseAgent
from db import get_db

# ─────────────────────────────────────────────────────────────────────────────
# Ticket Triage Agent
# ─────────────────────────────────────────────────────────────────────────────

_TRIAGE_SYSTEM = """You are MERGENT's Support Triage Agent.
Classify incoming support tickets and attempt auto-resolution for simple cases.

Return ONLY JSON:
{
  "type": "bug" | "billing" | "dispute" | "feature_request" | "general" | "refund",
  "urgency": "low" | "medium" | "high",
  "responsible_party": "buyer" | "builder" | "platform",
  "auto_resolvable": true | false,
  "auto_response": "response text if auto_resolvable=true, else null",
  "suggested_resolution": "one sentence on recommended resolution path",
  "escalate_immediately": true | false,
  "tags": ["tag1", "tag2"]
}
JSON only."""


class TicketTriageAgent(BaseAgent):
    agent_name = "TicketTriageAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        ticket = input.get("ticket", {}) or {}
        ticket_id = ticket.get("_id") or input.get("ticket_id")

        if not ticket and ticket_id:
            db = get_db()
            ticket = await db.support_tickets.find_one({"_id": ticket_id}) or {}

        if not ticket:
            return {"error": "ticket_not_found"}

        ticket_payload = {
            "title": ticket.get("title", ""),
            "description": ticket.get("description", ""),
            "submitted_by_role": ticket.get("submitted_by_role", "buyer"),
            "related_solution": ticket.get("related_solution_title", ""),
            "transaction_involved": bool(ticket.get("transaction_id")),
        }

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _TRIAGE_SYSTEM},
                {"role": "user", "content": f"Support ticket:\n{ticket_payload}\n\nReturn triage JSON now."},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=500,
        )

        db = get_db()
        update: Dict[str, Any] = {
            "triage_type": result.get("type", "general"),
            "urgency": result.get("urgency", "medium"),
            "responsible_party": result.get("responsible_party", "platform"),
            "auto_resolvable": result.get("auto_resolvable", False),
            "tags": result.get("tags", []),
            "triaged_at": datetime.now(timezone.utc),
        }

        # Auto-resolve simple tickets
        if result.get("auto_resolvable") and result.get("auto_response"):
            update["status"] = "resolved"
            update["resolution"] = result["auto_response"]
            update["resolved_at"] = datetime.now(timezone.utc)
            update["resolved_by"] = "TicketTriageAgent"

            # Notify submitter
            user_id = ticket.get("submitted_by")
            if user_id:
                await db.notifications.insert_one({
                    "user_id": user_id,
                    "type": "ticket_resolved",
                    "message": f"Your support ticket has been resolved: {result['auto_response'][:100]}",
                    "link": f"/support/tickets/{ticket_id}",
                    "read": False,
                    "created_at": datetime.now(timezone.utc),
                })

        # Immediate escalation for high urgency or disputes
        if result.get("escalate_immediately") or result.get("type") == "dispute":
            update["escalated"] = True
            update["escalated_at"] = datetime.now(timezone.utc)

        if ticket_id:
            await db.support_tickets.update_one({"_id": ticket_id}, {"$set": update})

        return {**result, "ticket_id": str(ticket_id), "_chat_result": chat_result}


# ─────────────────────────────────────────────────────────────────────────────
# Escalation Agent
# ─────────────────────────────────────────────────────────────────────────────

class EscalationAgent(BaseAgent):
    agent_name = "EscalationAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        ticket_id = input.get("ticket_id")
        ticket = input.get("ticket") or (
            await db.support_tickets.find_one({"_id": ticket_id}) if ticket_id else None
        ) or {}

        ticket_type = ticket.get("triage_type", "general")
        urgency = ticket.get("urgency", "medium")

        # Determine escalation path
        escalation_path = "platform_support"
        assigned_queue = "general"

        if ticket_type == "dispute":
            escalation_path = "escrow_dispute_resolution"
            assigned_queue = "disputes"
            # Create escrow dispute record
            if ticket.get("transaction_id"):
                await db.escrow_disputes.insert_one({
                    "ticket_id": ticket_id,
                    "transaction_id": ticket.get("transaction_id"),
                    "status": "open",
                    "created_at": datetime.now(timezone.utc),
                })

        elif ticket_type == "billing" or ticket_type == "refund":
            escalation_path = "finance_review"
            assigned_queue = "billing"

        elif urgency == "high" and ticket_type == "bug":
            escalation_path = "platform_engineering"
            assigned_queue = "critical_bugs"

        elif ticket_type == "feature_request":
            escalation_path = "product_team"
            assigned_queue = "feature_requests"

        update = {
            "escalated": True,
            "escalated_at": datetime.now(timezone.utc),
            "escalation_path": escalation_path,
            "assigned_queue": assigned_queue,
            "status": "escalated",
        }

        if ticket_id:
            await db.support_tickets.update_one({"_id": ticket_id}, {"$set": update})

            # Notify submitter of escalation
            user_id = ticket.get("submitted_by")
            if user_id:
                await db.notifications.insert_one({
                    "user_id": user_id,
                    "type": "ticket_escalated",
                    "message": f"Your support ticket has been escalated to {escalation_path.replace('_', ' ')}.",
                    "link": f"/support/tickets/{ticket_id}",
                    "read": False,
                    "created_at": datetime.now(timezone.utc),
                })

        return {
            "ticket_id": str(ticket_id),
            "escalation_path": escalation_path,
            "assigned_queue": assigned_queue,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Customer Success Agent (Celery beat — runs daily)
# ─────────────────────────────────────────────────────────────────────────────

_CS_SYSTEM = """You are MERGENT's Customer Success Agent.
Generate a personalized, helpful re-engagement message for an at-risk buyer.
Be genuinely helpful — not salesy. Focus on solving their problem.
Return ONLY JSON:
{
  "subject": "notification subject line",
  "message_body": "2-3 sentences — personalized, helpful, specific to their context",
  "suggested_categories": ["category 1", "category 2"],
  "call_to_action": "one action phrase e.g. 'Try searching for CRM solutions'"
}
JSON only."""


class CustomerSuccessAgent(BaseAgent):
    agent_name = "CustomerSuccessAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        now = datetime.now(timezone.utc)
        inactive_threshold = now - timedelta(days=14)
        nudge_count = 0

        # Find at-risk buyers
        at_risk_buyers = await self._find_at_risk_buyers(db, inactive_threshold)

        for buyer in at_risk_buyers:
            buyer_id = buyer.get("_id") or buyer.get("user_id")
            context = buyer.get("context", "browsed solutions but didn't purchase")

            result, _ = await self._llm(
                messages=[
                    {"role": "system", "content": _CS_SYSTEM},
                    {"role": "user", "content": (
                        f"Buyer context: {context}\n"
                        f"Last activity: {buyer.get('last_activity_days', 14)} days ago\n"
                        f"Categories browsed: {buyer.get('categories_browsed', [])}\n"
                        "Generate re-engagement message JSON now."
                    )},
                ],
                temperature=0.5,
                json_mode=True,
                max_tokens=400,
            )

            # Send in-app notification
            await db.notifications.insert_one({
                "user_id": buyer_id,
                "type": "customer_success_nudge",
                "message": result.get("message_body", ""),
                "call_to_action": result.get("call_to_action", ""),
                "suggested_categories": result.get("suggested_categories", []),
                "read": False,
                "created_at": now,
            })

            # Log for analytics
            await db.customer_success_log.insert_one({
                "buyer_id": buyer_id,
                "context": context,
                "message_sent": result.get("message_body", ""),
                "created_at": now,
            })
            nudge_count += 1

        return {"buyers_nudged": nudge_count, "run_at": now.isoformat()}

    async def _find_at_risk_buyers(
        self, db: Any, inactive_threshold: datetime
    ) -> List[Dict[str, Any]]:
        at_risk: List[Dict[str, Any]] = []

        # Buyers with no activity in 14 days
        inactive_cursor = db.users.find(
            {
                "role": "buyer",
                "last_active_at": {"$lt": inactive_threshold},
            },
            {"_id": 1, "last_active_at": 1},
        ).limit(50)

        async for user in inactive_cursor:
            user_id = user["_id"]
            purchase_count = await db.transactions.count_documents({"buyer_id": user_id})
            if purchase_count == 0:
                # Check what they browsed
                events = [d async for d in db.analytics_events.find(
                    {"user_id": user_id, "event_type": "solution_view"},
                    {"category": 1},
                ).limit(10)]
                categories = list({e.get("category", "") for e in events if e.get("category")})
                days_inactive = (datetime.now(timezone.utc) - user.get("last_active_at", inactive_threshold)).days
                at_risk.append({
                    "_id": user_id,
                    "context": "browsed solutions but hasn't purchased or returned",
                    "last_activity_days": days_inactive,
                    "categories_browsed": categories,
                })

        return at_risk


# Shim functions
async def run_triage(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await TicketTriageAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_escalation(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await EscalationAgent().execute(ctx, run_id=ctx.get("run_id"))

async def run_customer_success(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await CustomerSuccessAgent().execute(ctx, run_id=ctx.get("run_id"))
