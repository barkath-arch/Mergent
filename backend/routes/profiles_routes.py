"""Users / profiles / builders surface."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from db import get_db
from storage import save_data_uri

router = APIRouter(prefix="/api", tags=["profiles"])


class UpdateMeIn(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    avatar_data_uri: Optional[str] = None
    headline: Optional[str] = Field(None, max_length=200)
    bio: Optional[str] = Field(None, max_length=2000)
    skills: Optional[List[str]] = None
    company: Optional[str] = Field(None, max_length=200)
    industry: Optional[str] = Field(None, max_length=200)


def _builder_public(u: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": u["_id"],
        "name": u.get("name"),
        "email": u.get("email"),
        "avatar_url": u.get("avatar_url"),
        "headline": p.get("headline", ""),
        "bio": p.get("bio", ""),
        "skills": p.get("skills", []),
        "rating": p.get("rating", 0.0),
        "review_count": p.get("review_count", 0),
        "solutions_count": p.get("solutions_count", 0),
        "deployments_count": p.get("deployments_count", 0),
        "earnings_usd": p.get("earnings_usd", 0.0),
        "verified": p.get("verified", False),
        "joined_at": p.get("joined_at"),
    }


@router.patch("/me")
async def update_me(body: UpdateMeIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user_updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if body.name is not None:
        user_updates["name"] = body.name.strip()
    if body.avatar_data_uri:
        try:
            user_updates["avatar_url"] = save_data_uri(body.avatar_data_uri, namespace="avatar")
        except ValueError as e:
            raise HTTPException(400, detail={"error": str(e)})
    await db.users.update_one({"_id": user["id"]}, {"$set": user_updates})

    profile_coll = "builder_profiles" if user["role"] == "builder" else "buyer_profiles"
    profile_updates: Dict[str, Any] = {}
    if user["role"] == "builder":
        for f in ("headline", "bio", "skills"):
            v = getattr(body, f)
            if v is not None:
                profile_updates[f] = v
    else:
        for f in ("company", "industry"):
            v = getattr(body, f)
            if v is not None:
                profile_updates[f] = v
    if profile_updates:
        await db[profile_coll].update_one({"_id": user["id"]}, {"$set": profile_updates}, upsert=True)

    fresh_user = await db.users.find_one({"_id": user["id"]})
    fresh_user.pop("password_hash", None)
    fresh_user["id"] = fresh_user.pop("_id")
    return fresh_user


@router.get("/builders")
async def list_builders(
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("rating", pattern="^(rating|solutions|earnings|recent)$"),
) -> Dict[str, Any]:
    db = get_db()
    sort_key = {"rating": "rating", "solutions": "solutions_count",
                "earnings": "earnings_usd", "recent": "joined_at"}[sort]
    cursor = db.builder_profiles.find().sort(sort_key, -1).limit(limit)
    profiles = [p async for p in cursor]
    user_ids = [p["_id"] for p in profiles]
    users = {u["_id"]: u async for u in db.users.find({"_id": {"$in": user_ids}})}
    items = [_builder_public(users[p["_id"]], p) for p in profiles if p["_id"] in users]
    return {"items": items, "count": len(items)}


@router.get("/builders/{builder_id}")
async def get_builder(builder_id: str) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": builder_id, "role": "builder"})
    if not user:
        raise HTTPException(404, detail={"error": "builder_not_found"})
    profile = await db.builder_profiles.find_one({"_id": builder_id}) or {}
    solutions = [s async for s in db.solutions.find({"builder_id": builder_id}, {"embedding": 0}).limit(20)]
    # Latest reviews referencing this builder
    reviews = [r async for r in db.reviews.find({"builder_id": builder_id}).sort("created_at", -1).limit(10)]
    return {
        "builder": _builder_public(user, profile),
        "solutions": [{**s, "id": s.pop("_id")} for s in solutions],
        "reviews": [{**r, "id": r.pop("_id")} for r in reviews],
    }
