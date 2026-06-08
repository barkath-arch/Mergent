"""Marketplace endpoints — hybrid search, trending, overview, recent requirements."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from db import get_db

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _serialize_solution(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {**d}
    out["id"] = out.pop("_id")
    out.pop("embedding", None)
    return out


@router.get("/search")
async def search(
    q: Optional[str] = Query(None, description="free-text query"),
    category: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sort: str = Query("trust", pattern="^(trust|recent|price_asc|price_desc|rating)$"),
    limit: int = Query(24, ge=1, le=60),
    skip: int = Query(0, ge=0),
) -> Dict[str, Any]:
    db = get_db()
    filter_q: Dict[str, Any] = {}
    if category:
        filter_q["category"] = category
    if min_price is not None or max_price is not None:
        rng: Dict[str, Any] = {}
        if min_price is not None:
            rng["$gte"] = min_price
        if max_price is not None:
            rng["$lte"] = max_price
        filter_q["price_usd"] = rng
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        filter_q["$or"] = [
            {"title": rx}, {"tagline": rx}, {"description": rx},
            {"tags": rx}, {"tech_stack": rx}, {"builder_name": rx},
        ]

    sort_map = {
        "trust": [("trust_score", -1), ("builder_rating", -1)],
        "recent": [("created_at", -1)],
        "price_asc": [("price_usd", 1)],
        "price_desc": [("price_usd", -1)],
        "rating": [("builder_rating", -1)],
    }
    cursor = db.solutions.find(filter_q, {"embedding": 0}).sort(sort_map[sort]).skip(skip).limit(limit)
    items = [_serialize_solution(d) async for d in cursor]
    total = await db.solutions.count_documents(filter_q)
    return {"items": items, "total": total, "limit": limit, "skip": skip, "sort": sort}


@router.get("/trending")
async def trending(limit: int = Query(8, ge=1, le=20)) -> Dict[str, Any]:
    db = get_db()
    cursor = db.solutions.find({}, {"embedding": 0}).sort(
        [("clients_count", -1), ("builder_rating", -1)]
    ).limit(limit)
    items = [_serialize_solution(d) async for d in cursor]
    return {"items": items}


@router.get("/overview")
async def overview() -> Dict[str, Any]:
    db = get_db()
    total_solutions = await db.solutions.count_documents({})
    total_builders = await db.users.count_documents({"role": "builder"})
    total_transactions = await db.transactions.count_documents({"status": {"$in": ["released", "delivered", "in_progress"]}})
    total_volume_cursor = db.transactions.aggregate([
        {"$match": {"status": "released"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}}},
    ])
    total_volume = 0.0
    async for row in total_volume_cursor:
        total_volume = float(row.get("total", 0.0))

    # Top categories
    cat_cursor = db.solutions.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 6},
    ])
    categories = [{"name": row["_id"], "count": row["count"]} async for row in cat_cursor]

    # 24h activity counters
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    new_solutions_24h = await db.solutions.count_documents({"created_at": {"$gte": since}})
    new_runs_24h = await db.match_runs.count_documents({"created_at": {"$gte": since.isoformat()}})
    new_requirements_24h = await db.requirements.count_documents({"created_at": {"$gte": since}})

    return {
        "solutions": total_solutions,
        "builders": total_builders,
        "active_transactions": total_transactions,
        "gmv_released_usd": round(total_volume, 2),
        "categories": categories,
        "activity_24h": {
            "new_solutions": new_solutions_24h,
            "ai_match_runs": new_runs_24h,
            "new_requirements": new_requirements_24h,
        },
    }


@router.get("/requirements/recent")
async def recent_requirements(limit: int = Query(8, ge=1, le=20)) -> Dict[str, Any]:
    db = get_db()
    cursor = db.requirements.find().sort("created_at", -1).limit(limit)
    items: List[Dict[str, Any]] = []
    async for r in cursor:
        items.append({
            "id": r["_id"],
            "title": r.get("title"),
            "summary": (r.get("description") or "")[:200],
            "budget_usd": r.get("budget_usd"),
            "category": r.get("category"),
            "buyer_name": r.get("buyer_name", "Anonymous"),
            "created_at": r.get("created_at"),
            "match_count": r.get("match_count", 0),
        })
    return {"items": items}
