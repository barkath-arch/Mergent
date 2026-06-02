"""Mergent V1.6 — Trust & Quality Agent.

Replaces the V1 reactive review-only recompute with a multi-component score:
- 20% uptime (avg `uptime_pct` across listed solutions)
- 25% transaction success rate (released vs disputed/refunded over 90d)
- 20% review authenticity (rating variance + body length + time bursts)
- 10% response time (median first-reply on conversations)
- 15% volume & tenure (log-scaled txns + months on platform)
- 10% dispute penalty (subtract for unresolved last 180d)

Score persists on `builder_profiles.trust_score` and a capped history.

# SIMULATED: response-time component is best-effort with current message
# schema (no per-thread analytics yet); falls back to a neutral 50/100 when
# we lack 2+ ping/pong pairs. Documented and easily extended in Phase 8.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from statistics import median, pstdev
from typing import Any, Dict, List, Optional

from db import get_db

logger = logging.getLogger("services.trust_agent")

WEIGHTS = {"uptime": 0.20, "tx_success": 0.25, "reviews": 0.20, "response": 0.10,
           "volume_tenure": 0.15, "dispute_penalty": -0.10}
HISTORY_CAP = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


async def _uptime_component(db, builder_id: str) -> float:
    cur = db.solutions.aggregate([
        {"$match": {"builder_id": builder_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$uptime_pct"}, "n": {"$sum": 1}}},
    ])
    async for row in cur:
        if row.get("n", 0) > 0 and row.get("avg") is not None:
            return _clamp(float(row["avg"]))  # 0-100
    return 50.0  # neutral


async def _tx_success_component(db, builder_id: str) -> float:
    since = _now() - timedelta(days=90)
    cur = db.transactions.aggregate([
        {"$match": {"builder_id": builder_id, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ])
    counts: Dict[str, int] = {}
    async for row in cur:
        counts[row["_id"]] = int(row["n"])
    pos = counts.get("released", 0) + counts.get("reviewed", 0)
    neg = counts.get("refunded", 0) + counts.get("disputed", 0)
    total = pos + neg
    if total < 2:
        return 60.0  # mild positive baseline for new builders
    return _clamp(100.0 * pos / total)


async def _review_authenticity_component(db, builder_id: str) -> float:
    reviews = [r async for r in db.reviews.find({"builder_id": builder_id}).limit(200)]
    if len(reviews) < 3:
        return 55.0  # not enough data
    ratings = [int(r.get("rating", 5)) for r in reviews]
    bodies = [(r.get("comment") or "") for r in reviews]
    # 1. variance — too uniform = suspicious (low score), healthy = ~0.5-1.5
    var = pstdev(ratings) if len(ratings) > 1 else 0.0
    var_score = 100.0 if 0.4 <= var <= 1.6 else (60.0 if var < 0.4 else 80.0)
    # 2. body length sanity — median 30-300 chars healthy
    med_len = median([len(b) for b in bodies])
    if 25 <= med_len <= 350: len_score = 100.0
    elif 12 <= med_len < 25 or 350 < med_len <= 700: len_score = 75.0
    else: len_score = 50.0
    # 3. time bursts — count unique day buckets; high burstiness = suspicious
    days = {r.get("created_at").date() if isinstance(r.get("created_at"), datetime) else None for r in reviews}
    days.discard(None)
    spread = len(days) / max(1, len(reviews))  # 1.0 = each on its own day, 0.1 = all bunched
    burst_score = _clamp(20.0 + 80.0 * min(1.0, spread * 2))
    return _clamp(0.4 * var_score + 0.3 * len_score + 0.3 * burst_score)


async def _response_time_component(db, builder_id: str) -> float:
    """Best-effort: median time between any incoming message and the builder's next reply.
    SIMULATED-light: with current schema we approximate via per-thread first-reply.
    """
    convs = [c async for c in db.conversations.find({"participants": builder_id}).limit(50)]
    deltas: List[float] = []
    for c in convs:
        msgs = [m async for m in db.messages.find({"conversation_id": c["_id"]}).sort("created_at", 1).limit(20)]
        prev_other_at: Optional[datetime] = None
        for m in msgs:
            if m.get("sender_id") != builder_id:
                prev_other_at = m.get("created_at")
            elif prev_other_at is not None:
                d = m.get("created_at") - prev_other_at
                if isinstance(d, timedelta):
                    deltas.append(d.total_seconds() / 3600.0)  # hours
                prev_other_at = None
                break  # one delta per thread
    if len(deltas) < 2:
        return 50.0  # neutral
    med_hours = median(deltas)
    # target ≤ 24h = 100, 48h = 75, 72h = 50, 7d = 20
    if med_hours <= 24: return 100.0
    if med_hours <= 48: return 80.0
    if med_hours <= 72: return 60.0
    if med_hours <= 168: return 35.0
    return 15.0


async def _volume_tenure_component(db, builder_id: str) -> float:
    n_tx = await db.transactions.count_documents({"builder_id": builder_id, "status": {"$in": ["released", "reviewed", "delivered"]}})
    prof = await db.builder_profiles.find_one({"_id": builder_id}) or {}
    joined = prof.get("joined_at")
    months = 0.0
    if isinstance(joined, datetime):
        # Normalize naive datetimes (legacy seeded docs) to UTC to compare with aware _now().
        if joined.tzinfo is None:
            joined = joined.replace(tzinfo=timezone.utc)
        months = max(0.0, (_now() - joined).days / 30.0)
    # log-scale: 1 tx → 30, 10 → 60, 100 → 90; tenure: 1m → 30, 12m → 80
    tx_score = _clamp(20 + 25 * math.log1p(n_tx))
    tenure_score = _clamp(20 + 18 * math.log1p(months))
    return _clamp(0.6 * tx_score + 0.4 * tenure_score)


async def _dispute_penalty(db, builder_id: str) -> float:
    """Returns negative penalty score (subtract from final)."""
    since = _now() - timedelta(days=180)
    n = await db.transactions.count_documents({
        "builder_id": builder_id, "status": "disputed", "created_at": {"$gte": since},
    })
    return _clamp(min(100.0, n * 25.0))  # 4+ unresolved disputes → max penalty


async def compute_builder_trust(builder_id: str) -> Dict[str, Any]:
    db = get_db()
    uptime = await _uptime_component(db, builder_id)
    tx_succ = await _tx_success_component(db, builder_id)
    reviews = await _review_authenticity_component(db, builder_id)
    response = await _response_time_component(db, builder_id)
    vol_ten = await _volume_tenure_component(db, builder_id)
    dispute = await _dispute_penalty(db, builder_id)

    raw = (
        WEIGHTS["uptime"] * uptime +
        WEIGHTS["tx_success"] * tx_succ +
        WEIGHTS["reviews"] * reviews +
        WEIGHTS["response"] * response +
        WEIGHTS["volume_tenure"] * vol_ten +
        WEIGHTS["dispute_penalty"] * dispute
    )
    score = round(_clamp(raw), 2)
    components = {
        "uptime": round(uptime, 2),
        "tx_success": round(tx_succ, 2),
        "review_authenticity": round(reviews, 2),
        "response_time": round(response, 2),
        "volume_tenure": round(vol_ten, 2),
        "dispute_penalty": round(dispute, 2),
    }
    return {"score": score, "components": components, "computed_at": _now()}


async def persist_trust(builder_id: str) -> Dict[str, Any]:
    """Compute and persist. Append to history (capped)."""
    db = get_db()
    result = await compute_builder_trust(builder_id)
    history_entry = {"score": result["score"], "computed_at": result["computed_at"]}
    await db.builder_profiles.update_one(
        {"_id": builder_id},
        {"$set": {
            "trust_score": result["score"],
            "trust_score_components": result["components"],
            "trust_score_computed_at": result["computed_at"],
        }, "$push": {
            "trust_score_history": {"$each": [history_entry], "$slice": -HISTORY_CAP},
        }},
        upsert=True,
    )
    logger.info(f"trust_score_persisted builder_id={builder_id} score={result['score']}")
    return result


async def recompute_all() -> Dict[str, Any]:
    """Sweep every builder. Used by Celery beat nightly + on-demand."""
    db = get_db()
    builder_ids = [u["_id"] async for u in db.users.find({"role": "builder"}, {"_id": 1})]
    results = []
    for bid in builder_ids:
        try:
            results.append({"builder_id": bid, **(await persist_trust(bid))})
        except Exception as e:
            logger.warning(f"trust_recompute_failed builder_id={bid} err={e}")
    logger.info(f"trust_recompute_all done count={len(results)}")
    return {"count": len(results), "results": results}
