"""Audit log routes — `/api/audit/me` (self-view) and admin filter view."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from auth import get_current_user, require_role
from db import get_db

router = APIRouter(prefix="/api", tags=["audit"])


def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
    return {**row, "id": row.pop("_id")}


@router.get("/audit/me")
async def my_audit(
    user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> Dict[str, Any]:
    db = get_db()
    q = {"actor_user_id": user["id"]}
    items: List[Dict[str, Any]] = []
    async for row in db.audit_log.find(q).sort("ts", -1).skip(skip).limit(limit):
        items.append(_serialize(row))
    total = await db.audit_log.count_documents(q)
    return {"items": items, "total": total, "limit": limit, "skip": skip}


@router.get("/admin/audit")
async def admin_audit(
    user: Dict[str, Any] = Depends(require_role("admin")),
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    target_collection: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> Dict[str, Any]:
    db = get_db()
    q: Dict[str, Any] = {}
    if action: q["action"] = action
    if actor_user_id: q["actor_user_id"] = actor_user_id
    if target_collection: q["target_collection"] = target_collection
    items: List[Dict[str, Any]] = []
    async for row in db.audit_log.find(q).sort("ts", -1).skip(skip).limit(limit):
        items.append(_serialize(row))
    total = await db.audit_log.count_documents(q)
    return {"items": items, "total": total, "limit": limit, "skip": skip}
