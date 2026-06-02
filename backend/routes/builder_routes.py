"""Builder Hub — per-builder dashboard endpoints.

All endpoints require role=builder|admin. They aggregate views over the
existing solutions/transactions/reviews/deployments collections — no schema
changes here, just read-side projections.

Routes:
  GET /api/me/sales              — recent paid transactions + 30-day sparkline
  GET /api/me/earnings           — released-tx ledger + ytd / lifetime totals
  GET /api/me/stats              — solution-level performance table
  GET /api/builders/{id}/trust   — public trust-score + components + history
  POST /api/builders/me/trust/recompute   — admin/self trigger
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user, require_role
from db import get_db
from services.trust_agent import persist_trust

router = APIRouter(prefix="/api", tags=["builder"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------ /api/me/sales ------------------------------------
@router.get("/me/sales")
async def my_sales(
    user: Dict[str, Any] = Depends(require_role("builder", "admin")),
    days: int = Query(30, ge=7, le=365),
) -> Dict[str, Any]:
    db = get_db()
    since = _now() - timedelta(days=days)
    q = {"builder_id": user["id"], "created_at": {"$gte": since},
         "status": {"$in": ["funded", "in_progress", "delivered", "released", "reviewed"]}}
    items: List[Dict[str, Any]] = []
    async for t in db.transactions.find(q).sort("created_at", -1).limit(200):
        items.append({
            "id": t["_id"],
            "buyer_name": t.get("buyer_name"),
            "solution_id": t.get("solution_id"),
            "solution_title": t.get("solution_title"),
            "amount_usd": t.get("amount_usd"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
        })

    # Daily sparkline of funded volume.
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "amount": {"$sum": "$amount_usd"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    sparkline: List[Dict[str, Any]] = []
    async for row in db.transactions.aggregate(pipeline):
        sparkline.append({"date": row["_id"], "amount_usd": float(row.get("amount", 0)),
                          "count": int(row.get("count", 0))})

    return {"items": items, "count": len(items), "sparkline": sparkline,
            "window_days": days}


# ------------------------ /api/me/earnings ---------------------------------
@router.get("/me/earnings")
async def my_earnings(user: Dict[str, Any] = Depends(require_role("builder", "admin"))) -> Dict[str, Any]:
    db = get_db()
    profile = await db.builder_profiles.find_one({"_id": user["id"]}) or {}

    pipeline_lifetime = [
        {"$match": {"builder_id": user["id"], "status": {"$in": ["released", "reviewed"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}, "n": {"$sum": 1}}},
    ]
    lifetime = {"amount": 0.0, "count": 0}
    async for row in db.transactions.aggregate(pipeline_lifetime):
        lifetime = {"amount": float(row.get("total", 0.0)), "count": int(row.get("n", 0))}

    since_ytd = datetime(_now().year, 1, 1, tzinfo=timezone.utc)
    ytd = {"amount": 0.0, "count": 0}
    async for row in db.transactions.aggregate([
        {"$match": {"builder_id": user["id"], "status": {"$in": ["released", "reviewed"]},
                    "created_at": {"$gte": since_ytd}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}, "n": {"$sum": 1}}},
    ]):
        ytd = {"amount": float(row.get("total", 0.0)), "count": int(row.get("n", 0))}

    # Latest 30 released transactions for the ledger.
    ledger: List[Dict[str, Any]] = []
    async for t in db.transactions.find(
        {"builder_id": user["id"], "status": {"$in": ["released", "reviewed"]}}
    ).sort("created_at", -1).limit(30):
        ledger.append({
            "id": t["_id"],
            "solution_title": t.get("solution_title"),
            "buyer_name": t.get("buyer_name"),
            "amount_usd": float(t.get("amount_usd", 0)),
            "released_at": next(
                (s.get("at") for s in (t.get("state_history") or []) if s.get("state") == "released"),
                t.get("updated_at"),
            ),
        })

    return {
        "ledger_balance_usd": round(float(profile.get("earnings_usd", 0.0)), 2),
        "lifetime": {"amount_usd": round(lifetime["amount"], 2), "count": lifetime["count"]},
        "ytd": {"amount_usd": round(ytd["amount"], 2), "count": ytd["count"]},
        "ledger": ledger,
        "payout_provider_status": "simulated",  # SIMULATED — real Stripe Connect deferred to Phase 10
    }


# ------------------------ /api/me/stats ------------------------------------
@router.get("/me/stats")
async def my_stats(user: Dict[str, Any] = Depends(require_role("builder", "admin"))) -> Dict[str, Any]:
    db = get_db()
    sols: List[Dict[str, Any]] = []
    async for s in db.solutions.find({"builder_id": user["id"]}, {"embedding": 0}).limit(100):
        sid = s["_id"]
        tx_pipeline = [
            {"$match": {"solution_id": sid}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}, "amt": {"$sum": "$amount_usd"}}},
        ]
        by_status: Dict[str, Dict[str, float]] = {}
        async for row in db.transactions.aggregate(tx_pipeline):
            by_status[row["_id"]] = {"count": int(row["n"]), "amount": float(row.get("amt", 0))}
        gmv = sum(v["amount"] for k, v in by_status.items() if k in ("released", "reviewed"))
        review_n = await db.reviews.count_documents({"solution_id": sid})
        sols.append({
            "id": sid,
            "title": s.get("title"),
            "tagline": s.get("tagline"),
            "category": s.get("category"),
            "price_usd": s.get("price_usd"),
            "clients_count": s.get("clients_count", 0),
            "reviews_count": review_n,
            "gmv_released_usd": round(gmv, 2),
            "tx_by_status": by_status,
            "version": s.get("version", 1),
            "is_fork": s.get("is_fork", False),
            "fork_children_count": s.get("fork_children_count", 0),
            "uptime_pct": s.get("uptime_pct", 99.5),
        })

    deployments_n = await db.deployments.count_documents({"builder_id": user["id"]})
    return {"solutions": sols, "deployments_count": deployments_n}


# ------------------------ /api/me/overview ---------------------------------
@router.get("/me/overview")
async def my_overview(user: Dict[str, Any] = Depends(require_role("builder", "admin"))) -> Dict[str, Any]:
    """Compact dashboard tile data: 7d + 30d revenue, unread reviews,
    pending deliveries, total solutions, trust score.
    """
    db = get_db()
    now = _now()
    profile = await db.builder_profiles.find_one({"_id": user["id"]}) or {}

    async def _sum(since, statuses):
        amt = 0.0; n = 0
        async for row in db.transactions.aggregate([
            {"$match": {"builder_id": user["id"], "status": {"$in": statuses},
                        "created_at": {"$gte": since}}},
            {"$group": {"_id": None, "amt": {"$sum": "$amount_usd"}, "n": {"$sum": 1}}},
        ]):
            amt = float(row.get("amt", 0)); n = int(row.get("n", 0))
        return {"amount_usd": round(amt, 2), "count": n}

    rev_7d = await _sum(now - timedelta(days=7), ["released", "reviewed"])
    rev_30d = await _sum(now - timedelta(days=30), ["released", "reviewed"])
    pending = await db.transactions.count_documents(
        {"builder_id": user["id"], "status": {"$in": ["funded", "in_progress"]}}
    )
    n_solutions = await db.solutions.count_documents({"builder_id": user["id"]})

    # Recent activity feed
    activity: List[Dict[str, Any]] = []
    async for r in db.reviews.find({"builder_id": user["id"]}).sort("created_at", -1).limit(5):
        activity.append({"type": "review", "rating": r.get("rating"),
                         "buyer_name": r.get("buyer_name"),
                         "solution_id": r.get("solution_id"), "ts": r.get("created_at"),
                         "snippet": (r.get("comment") or "")[:140]})
    async for t in db.transactions.find(
        {"builder_id": user["id"]}, sort=[("updated_at", -1)]
    ).limit(5):
        activity.append({"type": "transaction", "status": t.get("status"),
                         "buyer_name": t.get("buyer_name"),
                         "solution_title": t.get("solution_title"),
                         "amount_usd": t.get("amount_usd"),
                         "ts": t.get("updated_at"), "id": t["_id"]})
    activity.sort(key=lambda a: a.get("ts") or now, reverse=True)
    activity = activity[:12]

    return {
        "revenue_7d": rev_7d,
        "revenue_30d": rev_30d,
        "pending_deliveries": pending,
        "solutions_count": n_solutions,
        "trust_score": profile.get("trust_score"),
        "trust_score_components": profile.get("trust_score_components"),
        "rating": profile.get("rating", 0.0),
        "review_count": profile.get("review_count", 0),
        "activity": activity,
    }


# ------------------------ Trust ---------------------------------------------
@router.get("/builders/{builder_id}/trust")
async def builder_trust(builder_id: str) -> Dict[str, Any]:
    db = get_db()
    profile = await db.builder_profiles.find_one({"_id": builder_id})
    if not profile:
        raise HTTPException(404, detail={"error": "builder_not_found"})
    return {
        "builder_id": builder_id,
        "score": profile.get("trust_score"),
        "components": profile.get("trust_score_components") or {},
        "computed_at": profile.get("trust_score_computed_at"),
        "history": profile.get("trust_score_history") or [],
    }


@router.post("/builders/me/trust/recompute")
async def trust_recompute_me(user: Dict[str, Any] = Depends(require_role("builder", "admin"))) -> Dict[str, Any]:
    result = await persist_trust(user["id"])
    return {"ok": True, **result}
