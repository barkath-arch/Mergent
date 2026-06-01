"""IntakeAgent — normalises user input and extracts cheap heuristic signals."""
from __future__ import annotations

import re
from typing import Any, Dict


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


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    requirement_text: str = ctx["requirement_text"]
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
