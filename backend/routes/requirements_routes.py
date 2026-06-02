"""Requirements — buyer-side posts that builders can browse."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user, require_role
from db import get_db

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


class RequirementCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=20, max_length=6000)
    category: str = Field(min_length=2, max_length=100)
    budget_usd: Optional[float] = Field(None, ge=0, le=1_000_000)
    timeline: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list)


def _serialize(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {**r}
    out["id"] = out.pop("_id")
    return out


@router.post("", status_code=201)
async def create_requirement(
    body: RequirementCreate, user: Dict[str, Any] = Depends(require_role("buyer", "admin"))
) -> Dict[str, Any]:
    db = get_db()
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "_id": rid,
        "buyer_id": user["id"],
        "buyer_name": user.get("name") or user.get("email"),
        "title": body.title.strip(),
        "description": body.description.strip(),
        "category": body.category,
        "budget_usd": float(body.budget_usd) if body.budget_usd is not None else None,
        "timeline": body.timeline,
        "tags": [t.strip() for t in body.tags if t.strip()][:20],
        "match_count": 0,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    await db.requirements.insert_one(doc)
    return _serialize(doc)


@router.get("")
async def list_requirements(
    category: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(open|matched|closed)$"),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    if status:
        q["status"] = status
    items = [_serialize(r) async for r in db.requirements.find(q).sort("created_at", -1).limit(limit)]
    return {"items": items, "count": len(items)}


@router.get("/{requirement_id}")
async def get_requirement(requirement_id: str) -> Dict[str, Any]:
    db = get_db()
    r = await db.requirements.find_one({"_id": requirement_id})
    if not r:
        raise HTTPException(404, detail={"error": "requirement_not_found"})
    return _serialize(r)


@router.get("/me/list")
async def my_requirements(user: Dict[str, Any] = Depends(require_role("buyer", "admin"))) -> Dict[str, Any]:
    db = get_db()
    items = [_serialize(r) async for r in db.requirements.find({"buyer_id": user["id"]}).sort("created_at", -1).limit(50)]
    return {"items": items, "count": len(items)}
