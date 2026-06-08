"""RequirementParserAgent — LLM call (JSON mode) → ParsedRequirement.

Phase AGENTS Step 1: subclass of `BaseAgent`; LLM call routed through
`self._llm(json_mode=True)` so `ai_usage_logs` records `agent_name`.
"""
from __future__ import annotations

from typing import Any, Dict

from pydantic import ValidationError

from agents.base import BaseAgent
from models import ParsedRequirement

_SYSTEM_PROMPT = """You are MERGENT's requirement-parsing agent.
Given a free-text software requirement, extract a strictly-typed JSON object describing what the user needs.

Return ONLY a JSON object with these keys:
{
  "category": "string — short product category name e.g. 'Inventory Management', 'CRM', 'HR System'",
  "business_domain": "string — industry/domain e.g. 'Textile Manufacturing', 'Healthcare', 'E-commerce'",
  "required_features": ["list of explicit features the user wants"],
  "tech_preferences": ["list of tech stack hints if mentioned, otherwise empty"],
  "saas_or_internal": "one of: 'saas' | 'internal' | 'unknown'",
  "deployment_complexity": "one of: 'MVP' | 'production-grade' | 'enterprise' | 'unknown'",
  "compliance_requirements": ["e.g. GDPR, HIPAA, SOC2 — empty list if none"]
}
Do NOT include any explanation or markdown. JSON only.
"""


class RequirementParserAgent(BaseAgent):
    agent_name = "RequirementParserAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        text = input["normalized_text"]
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Requirement:\n{text}\n\nReturn the JSON now."},
        ]
        parsed_dict, chat_result = await self._llm(
            messages=messages,
            temperature=0.0,
            json_mode=True,
            max_tokens=1200,
        )

        try:
            parsed = ParsedRequirement(**parsed_dict)
        except ValidationError as exc:
            safe = {
                "category": str(parsed_dict.get("category", "Unknown")),
                "business_domain": str(parsed_dict.get("business_domain", "General")),
                "required_features": list(parsed_dict.get("required_features", []) or []),
                "tech_preferences": list(parsed_dict.get("tech_preferences", []) or []),
                "saas_or_internal": str(parsed_dict.get("saas_or_internal", "unknown")),
                "deployment_complexity": str(parsed_dict.get("deployment_complexity", "unknown")),
                "compliance_requirements": list(parsed_dict.get("compliance_requirements", []) or []),
            }
            try:
                parsed = ParsedRequirement(**safe)
            except ValidationError:
                raise RuntimeError(f"RequirementParserAgent: validation failed - {exc}")

        return {
            "parsed_requirement": parsed.model_dump(),
            "_chat_result": chat_result,
        }


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await RequirementParserAgent().execute(ctx, run_id=ctx.get("run_id"))
