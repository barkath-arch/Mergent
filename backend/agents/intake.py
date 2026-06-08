"""IntakeAgent — normalises user input and extracts cheap heuristic signals.

Phase AGENTS Step 1: now a `BaseAgent` subclass. Module-level `run(ctx)` is
kept as a thin shim so the orchestrator's static PIPELINE keeps working.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from agents.base import BaseAgent


_BUDGET_RE = re.compile(r"(?:\$|usd|inr|₹|€|£)\s?(\d[\d,\.]*)\s?(k|m|thousand|million)?", re.IGNORECASE)
_URGENCY_KEYWORDS = ("urgent", "asap", "this week", "immediately", "today", "yesterday")
_MATURITY_HINTS = {
    "MVP": ("mvp", "prototype", "poc", "proof of concept", "quick"),
    "production-grade": ("production", "enterprise", "production-grade", "scalable", "high-availability", "ha"),
}


def _detect_budget(text: str) -> Dict[str, Any]:
    matches = _BUDGET_RE.findall(text)
    if not matches:
        return {"detected": False}
    amount_raw, suffix = matches[0]
    amount: float = 0.0
    try:
        amount = float(amount_raw.replace(",", ""))
    except ValueError:
        return {"detected": False}
    suffix = (suffix or "").lower()
    if suffix in ("k", "thousand"):
        amount *= 1000
    elif suffix in ("m", "million"):
        amount *= 1_000_000
    return {"detected": True, "amount_usd_estimate": amount}


def _detect_urgency(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _URGENCY_KEYWORDS)


def _detect_maturity(text: str) -> str:
    low = text.lower()
    for label, kws in _MATURITY_HINTS.items():
        if any(kw in low for kw in kws):
            return label
    return "unspecified"


class IntakeAgent(BaseAgent):
    agent_name = "IntakeAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        requirement_text: str = input["requirement_text"]
        normalized = " ".join(requirement_text.split()).strip()
        signals = {
            "budget": _detect_budget(normalized),
            "urgency": _detect_urgency(normalized),
            "deployment_maturity_hint": _detect_maturity(normalized),
            "char_len": len(normalized),
            "token_estimate": len(normalized) // 4,
        }
        return {
            "normalized_text": normalized,
            "signals": signals,
        }


# ---------------------------------------------------------------------------
# Module-level shim — keeps the orchestrator's static PIPELINE working.
# ---------------------------------------------------------------------------
async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await IntakeAgent().execute(ctx, run_id=ctx.get("run_id"))
