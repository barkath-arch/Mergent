"""Saved Items / Wishlist routes (Phase 7).

Endpoints:
  GET    /api/me/saved              — list saved solutions (with denormalized solution snapshot)
  POST   /api/me/saved              — save a solution (idempotent)
  DELETE /api/me/saved/{solution_id} — unsave
  GET    /api/me/saved/exists?ids=  — bulk-check (used by SolutionCard bookmark state)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from db import get_db

router = APIRouter(prefix="/api", tags=["saved_items"])


class SaveIn(BaseModel):
    solution_id: str
    note: Optional[str] = Field(None, max_length=400)


@router.get("/me/saved")
async def list_saved(
    user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    items: List[Dict[str, Any]] = []
    async for row in db.saved_items.find({"user_id": user["id"]}).sort("saved_at", -1).limit(limit):
        sol = await db.solutions.find_one(
            {"_id": row["solution_id"]},
            {"embedding": 0, "description": 0},
        )
        if not sol:
            continue
        items.append({
            "id": row["_id"],
            "solution_id": row["solution_id"],
            "saved_at": row.get("saved_at"),
            "note": row.get("note"),
            "solution": {**sol, "id": sol.pop("_id")},
        })
    return {"items": items, "count": len(items)}


@router.post("/me/saved", status_code=201)
async def save_item(body: SaveIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    sol = await db.solutions.find_one({"_id": body.solution_id}, {"_id": 1, "title": 1})
    if not sol:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    existing = await db.saved_items.find_one({"user_id": user["id"], "solution_id": body.solution_id})
    if existing:
        if body.note is not None and body.note != existing.get("note"):
            await db.saved_items.update_one({"_id": existing["_id"]}, {"$set": {"note": body.note}})
        return {"id": existing["_id"], "solution_id": body.solution_id, "already": True}
    sid = str(uuid.uuid4())
    await db.saved_items.insert_one({
        "_id": sid, "user_id": user["id"], "solution_id": body.solution_id,
        "note": body.note, "saved_at": datetime.now(timezone.utc),
    })
    return {"id": sid, "solution_id": body.solution_id, "already": False}


@router.delete("/me/saved/{solution_id}")
async def unsave(solution_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    res = await db.saved_items.delete_one({"user_id": user["id"], "solution_id": solution_id})
    return {"deleted": res.deleted_count}


@router.get("/me/saved/exists")
async def saved_exists(
    user: Dict[str, Any] = Depends(get_current_user),
    ids: str = Query("", description="comma-separated solution ids"),
) -> Dict[str, Any]:
    sid_list = [s.strip() for s in ids.split(",") if s.strip()]
    if not sid_list:
        return {"saved": {}}
    db = get_db()
    out: Dict[str, bool] = {sid: False for sid in sid_list}
    async for row in db.saved_items.find({"user_id": user["id"], "solution_id": {"$in": sid_list}}):
        out[row["solution_id"]] = True
    return {"saved": out}
