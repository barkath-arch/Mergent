"""ComplianceAgent — checks listings against platform policies.

Triggered on solution create/update alongside TrustAuditorAgent.
If compliant=false and severity=critical → rejects listing and notifies builder.
If severity=warning → adds warning badge and notifies builder.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base import BaseAgent
from db import get_db

_SYSTEM_PROMPT = """You are MERGENT's Compliance Agent.
Review this software listing against MERGENT platform policies.

PROHIBITED categories (reject immediately):
- Adult/explicit content tools
- Tools designed for unauthorized data harvesting or scraping
- Malware, spyware, surveillance tools
- Gambling systems
- Tools that facilitate illegal activities
- Fake review generation tools
- Spam or phishing infrastructure

WARNING categories (allow with warning):
- Tools with ambiguous data privacy practices
- Tools claiming government/enterprise compliance without evidence
- Tools in heavily regulated industries (healthcare, finance) without compliance notes
- Cryptocurrency tools without appropriate disclosures

Return ONLY JSON:
{
  "compliant": true | false,
  "violations": ["specific violation 1", "specific violation 2"],
  "warnings": ["warning 1", "warning 2"],
  "severity": "none" | "warning" | "critical",
  "category_flags": ["categories that triggered review"],
  "reasoning": "one sentence"
}
JSON only.
"""


class ComplianceAgent(BaseAgent):
    agent_name = "ComplianceAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"compliant": True, "violations": [], "warnings": [], "severity": "none"}

        listing_payload = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tags": solution.get("tags", []),
            "tech_stack": solution.get("tech_stack", []),
        }

        user_msg = (
            f"Listing to review for compliance:\n{listing_payload}\n\n"
            "Return the compliance JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            json_mode=True,
            max_tokens=500,
        )

        compliant = bool(result.get("compliant", True))
        severity = result.get("severity", "none")
        violations = result.get("violations", [])
        warnings = result.get("warnings", [])

        if solution_id:
            db = get_db()
            update: Dict[str, Any] = {
                "compliance_result": {
                    "compliant": compliant,
                    "violations": violations,
                    "warnings": warnings,
                    "severity": severity,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            }

            if not compliant and severity == "critical":
                update["status"] = "rejected"
                update["rejection_reason"] = f"Compliance violation: {result.get('reasoning', '')}"
                # Notify builder via notifications collection
                builder_id = solution.get("builder_id")
                if builder_id:
                    await db.notifications.insert_one({
                        "user_id": builder_id,
                        "type": "compliance_rejection",
                        "message": f"Your listing '{solution.get('title', '')}' was rejected: {result.get('reasoning', '')}",
                        "link": f"/solutions/{solution_id}",
                        "read": False,
                        "created_at": datetime.now(timezone.utc),
                    })

            elif severity == "warning" and warnings:
                update["compliance_warning"] = True
                builder_id = solution.get("builder_id")
                if builder_id:
                    await db.notifications.insert_one({
                        "user_id": builder_id,
                        "type": "compliance_warning",
                        "message": f"Your listing '{solution.get('title', '')}' has compliance notes: {'; '.join(warnings)}",
                        "link": f"/solutions/{solution_id}",
                        "read": False,
                        "created_at": datetime.now(timezone.utc),
                    })

            await db.solutions.update_one({"_id": solution_id}, {"$set": update})

        return {
            "compliant": compliant,
            "violations": violations,
            "warnings": warnings,
            "severity": severity,
            "category_flags": result.get("category_flags", []),
            "reasoning": result.get("reasoning", ""),
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await ComplianceAgent().execute(ctx, run_id=ctx.get("run_id"))
