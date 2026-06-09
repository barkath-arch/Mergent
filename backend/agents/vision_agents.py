"""Vision Intelligence Agents — GPT-4o Vision powered quality inspection.

Four agents that analyze screenshots and solution metadata:
  UIAuditAgent           — UI quality from screenshots
  UXAuditAgent           — Usability from screenshots
  ArchitectureExplanationAgent — Plain-English tech overview (no vision needed)
  SecurityAuditAgent     — Risk analysis from description + screenshots

All triggered on solution create/update when screenshots are uploaded.
Results stored in solutions collection.
Exposed via GET /api/solutions/{id}/vision-audit
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from agents.base import BaseAgent
from db import get_db


async def _fetch_image_b64(url: str) -> Optional[str]:
    """Fetch image from URL and return as base64 string."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return base64.b64encode(resp.content).decode("utf-8")
    except Exception:
        pass
    return None


def _build_vision_messages(
    system_prompt: str,
    text_prompt: str,
    image_urls: List[str],
    max_images: int = 3,
) -> List[Dict[str, Any]]:
    """Build messages list with inline images for GPT-4o Vision."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": text_prompt}]
    for url in image_urls[:max_images]:
        content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "low"},
        })
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# UI Audit Agent
# ─────────────────────────────────────────────────────────────────────────────

_UI_SYSTEM = """You are a UI quality auditor for software products.
Analyze the provided screenshots for UI quality.
Return ONLY JSON:
{
  "ui_score": 0-100,
  "layout_consistency": 0-100,
  "visual_hierarchy": 0-100,
  "component_quality": 0-100,
  "color_system": 0-100,
  "typography": 0-100,
  "issues": ["specific UI issue 1", "specific UI issue 2"],
  "highlights": ["positive aspect 1", "positive aspect 2"],
  "summary": "one sentence verdict"
}
JSON only."""


class UIAuditAgent(BaseAgent):
    agent_name = "UIAuditAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution_id = input.get("solution_id")
        screenshot_urls: List[str] = input.get("screenshot_urls", []) or []

        if not screenshot_urls:
            return {"ui_score": None, "skipped": True, "reason": "no_screenshots"}

        messages = _build_vision_messages(
            system_prompt=_UI_SYSTEM,
            text_prompt=f"Analyze these {len(screenshot_urls[:3])} screenshots for UI quality. Return the JSON now.",
            image_urls=screenshot_urls,
        )

        result, chat_result = await self._llm(
            messages=messages,
            temperature=0.1,
            json_mode=True,
            max_tokens=600,
        )

        ui_score = max(0, min(100, int(result.get("ui_score", 50))))

        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "ui_audit_result": {
                        **result,
                        "ui_score": ui_score,
                        "audited_at": datetime.now(timezone.utc).isoformat(),
                    }
                }},
            )

        return {**result, "ui_score": ui_score, "_chat_result": chat_result}


# ─────────────────────────────────────────────────────────────────────────────
# UX Audit Agent
# ─────────────────────────────────────────────────────────────────────────────

_UX_SYSTEM = """You are a UX usability auditor for software products.
Analyze the provided screenshots for usability and user experience quality.
Return ONLY JSON:
{
  "ux_score": 0-100,
  "navigation_clarity": 0-100,
  "cta_effectiveness": 0-100,
  "information_density": 0-100,
  "onboarding_clarity": 0-100,
  "friction_points": ["specific friction point 1", "friction point 2"],
  "recommendations": ["improvement 1", "improvement 2"],
  "summary": "one sentence verdict"
}
JSON only."""


class UXAuditAgent(BaseAgent):
    agent_name = "UXAuditAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution_id = input.get("solution_id")
        screenshot_urls: List[str] = input.get("screenshot_urls", []) or []

        if not screenshot_urls:
            return {"ux_score": None, "skipped": True, "reason": "no_screenshots"}

        messages = _build_vision_messages(
            system_prompt=_UX_SYSTEM,
            text_prompt=f"Analyze these {len(screenshot_urls[:3])} screenshots for UX quality. Return JSON now.",
            image_urls=screenshot_urls,
        )

        result, chat_result = await self._llm(
            messages=messages,
            temperature=0.1,
            json_mode=True,
            max_tokens=600,
        )

        ux_score = max(0, min(100, int(result.get("ux_score", 50))))

        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "ux_audit_result": {
                        **result,
                        "ux_score": ux_score,
                        "audited_at": datetime.now(timezone.utc).isoformat(),
                    }
                }},
            )

        return {**result, "ux_score": ux_score, "_chat_result": chat_result}


# ─────────────────────────────────────────────────────────────────────────────
# Architecture Explanation Agent (no vision — text only)
# ─────────────────────────────────────────────────────────────────────────────

_ARCH_SYSTEM = """You are a technical explainer for non-technical software buyers.
Given a software solution's details, explain its architecture in plain English.
Return ONLY JSON:
{
  "stack_summary": "2 sentences in plain English — what it's built on and why that matters",
  "complexity": "simple" | "moderate" | "complex",
  "integration_points": ["API 1", "service 2", "database 3"],
  "maintenance_level": "low" | "medium" | "high",
  "scalability": "poor" | "good" | "excellent",
  "technical_debt_risk": "low" | "medium" | "high",
  "hosting_requirements": "one sentence on what infrastructure is needed",
  "buyer_technical_requirement": "none" | "basic" | "intermediate" | "advanced"
}
JSON only."""


class ArchitectureExplanationAgent(BaseAgent):
    agent_name = "ArchitectureExplanationAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"error": "solution_not_found"}

        payload = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "category": solution.get("category", ""),
            "tech_stack": solution.get("tech_stack", []),
            "tags": solution.get("tags", []),
            "deployment_maturity": solution.get("deployment_maturity", ""),
        }

        user_msg = (
            f"Software solution:\n{payload}\n\n"
            "Explain the architecture for a non-technical buyer. Return JSON now."
        )

        result, chat_result = await self._llm(
            messages=[
                {"role": "system", "content": _ARCH_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=600,
        )

        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {
                    "architecture_explanation": {
                        **result,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    }
                }},
            )

        return {**result, "_chat_result": chat_result}


# ─────────────────────────────────────────────────────────────────────────────
# Security Audit Agent
# ─────────────────────────────────────────────────────────────────────────────

_SECURITY_TEXT_SYSTEM = """You are a software security reviewer.
Based on this solution's description and tech stack, identify potential security concerns a buyer should know about.
Return ONLY JSON:
{
  "risk_score": 0-100 (0=no risk, 100=critical risk),
  "vulnerabilities": ["specific concern 1", "concern 2"],
  "severity": "low" | "medium" | "high" | "critical",
  "recommendations": ["mitigation 1", "mitigation 2"],
  "compliance_notes": ["GDPR note", "data storage note"],
  "summary": "one sentence overall security posture"
}
JSON only."""

_SECURITY_VISION_SYSTEM = """You are a UI security reviewer.
Look at these screenshots for security red flags: exposed API keys or tokens visible in UI,
sensitive data shown without masking, missing authentication gates, debug information exposed.
Return ONLY JSON:
{
  "visual_security_issues": ["issue 1", "issue 2"],
  "severity": "none" | "low" | "medium" | "high"
}
JSON only."""


class SecurityAuditAgent(BaseAgent):
    agent_name = "SecurityAuditAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        solution = input.get("solution", {}) or {}
        solution_id = solution.get("_id") or input.get("solution_id")
        screenshot_urls: List[str] = input.get("screenshot_urls", []) or []

        if not solution and solution_id:
            db = get_db()
            solution = await db.solutions.find_one({"_id": solution_id}) or {}

        if not solution:
            return {"error": "solution_not_found"}

        # Part A: Text-based security analysis
        text_payload = {
            "title": solution.get("title", ""),
            "description": solution.get("description", ""),
            "tech_stack": solution.get("tech_stack", []),
            "category": solution.get("category", ""),
            "tags": solution.get("tags", []),
        }

        text_result, _ = await self._llm(
            messages=[
                {"role": "system", "content": _SECURITY_TEXT_SYSTEM},
                {"role": "user", "content": f"Solution to review:\n{text_payload}\n\nReturn security JSON now."},
            ],
            temperature=0.1,
            json_mode=True,
            max_tokens=600,
        )

        # Part B: Vision-based scan (if screenshots available)
        vision_result: Dict[str, Any] = {"visual_security_issues": [], "severity": "none"}
        if screenshot_urls:
            messages = _build_vision_messages(
                system_prompt=_SECURITY_VISION_SYSTEM,
                text_prompt="Scan these screenshots for security red flags. Return JSON now.",
                image_urls=screenshot_urls,
                max_images=3,
            )
            vision_result, _ = await self._llm(
                messages=messages,
                temperature=0.0,
                json_mode=True,
                max_tokens=400,
            )

        # Combine results
        all_vulnerabilities = (
            text_result.get("vulnerabilities", [])
            + vision_result.get("visual_security_issues", [])
        )

        severity_order = ["none", "low", "medium", "high", "critical"]
        text_sev = text_result.get("severity", "low")
        vision_sev = vision_result.get("severity", "none")
        combined_severity = severity_order[max(
            severity_order.index(text_sev) if text_sev in severity_order else 1,
            severity_order.index(vision_sev) if vision_sev in severity_order else 0,
        )]

        risk_score = max(0, min(100, int(text_result.get("risk_score", 0))))

        security_result = {
            "risk_score": risk_score,
            "vulnerabilities": all_vulnerabilities,
            "severity": combined_severity,
            "recommendations": text_result.get("recommendations", []),
            "compliance_notes": text_result.get("compliance_notes", []),
            "visual_issues": vision_result.get("visual_security_issues", []),
            "summary": text_result.get("summary", ""),
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

        if solution_id:
            db = get_db()
            await db.solutions.update_one(
                {"_id": solution_id},
                {"$set": {"security_audit_result": security_result}},
            )
            # Flag high/critical to admin
            if combined_severity in ("high", "critical"):
                await db.admin_flags.insert_one({
                    "entity_type": "solution",
                    "entity_id": solution_id,
                    "reason": f"Security audit: {combined_severity} severity — {text_result.get('summary', '')}",
                    "severity": combined_severity,
                    "created_at": datetime.now(timezone.utc),
                    "resolved": False,
                })

        return security_result


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await SecurityAuditAgent().execute(ctx, run_id=ctx.get("run_id"))
