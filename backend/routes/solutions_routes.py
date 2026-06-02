"""Solution CRUD + builder-side create/update with Celery-embed dispatch."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user, optional_user, require_role
from db import get_db
from storage import save_data_uri

router = APIRouter(prefix="/api", tags=["solutions"])

VALID_CATEGORIES = [
    "Inventory Management", "CRM", "HR System", "Project Management",
    "E-commerce", "Finance", "Analytics", "Marketing", "Operations", "Other",
]


class SolutionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    tagline: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=20, max_length=5000)
    category: str
    tech_stack: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    price_usd: float = Field(ge=0, le=1_000_000)
    license_model: str = Field(default="subscription", max_length=50)
    deployment_maturity: str = Field(default="production", max_length=50)
    demo_url: Optional[str] = None
    repo_url: Optional[str] = None
    screenshots_data_uris: List[str] = Field(default_factory=list, max_length=8)


class SolutionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=120)
    tagline: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=20, max_length=5000)
    category: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    price_usd: Optional[float] = Field(None, ge=0, le=1_000_000)
    license_model: Optional[str] = None
    deployment_maturity: Optional[str] = None
    demo_url: Optional[str] = None
    repo_url: Optional[str] = None
    screenshots_data_uris: Optional[List[str]] = None


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = {**doc}
    out["id"] = out.pop("_id")
    out.pop("embedding", None)
    return out


def _enqueue_embed(solution_id: str) -> None:
    try:
        from tasks import embed_solution
        embed_solution.apply_async(args=[solution_id], queue="mergent")
    except Exception as e:
        print(f"[mergent.solutions] enqueue_embed_failed sid={solution_id} err={e}")


@router.post("/solutions", status_code=201)
async def create_solution(
    body: SolutionCreate, user: Dict[str, Any] = Depends(require_role("builder", "admin"))
) -> Dict[str, Any]:
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, detail={"error": "invalid_category", "allowed": VALID_CATEGORIES})
    db = get_db()
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    screenshots: List[str] = []
    for uri in body.screenshots_data_uris:
        try:
            screenshots.append(save_data_uri(uri, namespace="screenshot"))
        except ValueError as e:
            raise HTTPException(400, detail={"error": str(e)})
    builder_profile = await db.builder_profiles.find_one({"_id": user["id"]}) or {}
    doc = {
        "_id": sid,
        "title": body.title.strip(),
        "tagline": body.tagline.strip(),
        "description": body.description.strip(),
        "category": body.category,
        "tech_stack": [t.strip() for t in body.tech_stack if t.strip()][:20],
        "tags": [t.strip() for t in body.tags if t.strip()][:20],
        "price_usd": float(body.price_usd),
        "license_model": body.license_model,
        "deployment_maturity": body.deployment_maturity,
        "demo_url": body.demo_url,
        "repo_url": body.repo_url,
        "screenshots": screenshots,
        "builder_id": user["id"],
        "builder_name": user.get("name") or user.get("email"),
        "builder_rating": float(builder_profile.get("rating", 0.0)),
        "uptime_pct": 99.5,
        "clients_count": 0,
        "trust_score": 0.0,
        "created_at": now,
        "updated_at": now,
    }
    await db.solutions.insert_one(doc)
    await db.builder_profiles.update_one(
        {"_id": user["id"]}, {"$inc": {"solutions_count": 1}}, upsert=True
    )
    _enqueue_embed(sid)
    return _serialize(doc)


@router.get("/solutions/{solution_id}")
async def get_solution(
    solution_id: str, user: Optional[Dict[str, Any]] = Depends(optional_user)
) -> Dict[str, Any]:
    db = get_db()
    doc = await db.solutions.find_one({"_id": solution_id})
    if not doc:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    out = _serialize(doc)
    builder = await db.builder_profiles.find_one({"_id": doc["builder_id"]})
    if builder:
        out["builder"] = {
            "id": builder["_id"],
            "name": doc.get("builder_name"),
            "rating": builder.get("rating", 0.0),
            "review_count": builder.get("review_count", 0),
            "headline": builder.get("headline", ""),
            "verified": builder.get("verified", False),
        }
    reviews = [r async for r in db.reviews.find({"solution_id": solution_id}).sort("created_at", -1).limit(20)]
    out["reviews"] = [{**r, "id": r.pop("_id")} for r in reviews]
    return out


@router.patch("/solutions/{solution_id}")
async def update_solution(
    solution_id: str, body: SolutionUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = get_db()
    doc = await db.solutions.find_one({"_id": solution_id})
    if not doc:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    if doc["builder_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_owner"})

    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    for k in ("title", "tagline", "description", "category", "tech_stack", "tags",
              "price_usd", "license_model", "deployment_maturity", "demo_url", "repo_url"):
        v = getattr(body, k)
        if v is not None:
            update[k] = v
    if body.screenshots_data_uris is not None:
        new_screens: List[str] = []
        for uri in body.screenshots_data_uris:
            if uri.startswith("/api/files/"):
                new_screens.append(uri)
            else:
                try:
                    new_screens.append(save_data_uri(uri, namespace="screenshot"))
                except ValueError as e:
                    raise HTTPException(400, detail={"error": str(e)})
        update["screenshots"] = new_screens
    await db.solutions.update_one({"_id": solution_id}, {"$set": update})
    if any(k in update for k in ("description", "tagline", "title", "tech_stack", "tags", "category")):
        _enqueue_embed(solution_id)
    fresh = await db.solutions.find_one({"_id": solution_id})
    return _serialize(fresh)


@router.delete("/solutions/{solution_id}")
async def delete_solution(solution_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    doc = await db.solutions.find_one({"_id": solution_id})
    if not doc:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    if doc["builder_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_owner"})
    await db.solutions.delete_one({"_id": solution_id})
    await db.builder_profiles.update_one(
        {"_id": doc["builder_id"]}, {"$inc": {"solutions_count": -1}}
    )
    return {"deleted": True, "id": solution_id}


@router.get("/me/solutions")
async def my_solutions(user: Dict[str, Any] = Depends(require_role("builder", "admin"))) -> Dict[str, Any]:
    db = get_db()
    items = [
        _serialize(d) async for d in
        db.solutions.find({"builder_id": user["id"]}).sort("created_at", -1).limit(50)
    ]
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Forking stub (Phase 9). Returns 501 but validates the schema and lineage
# so the contract is testable + frontend can wire a "Fork" button safely.
# ---------------------------------------------------------------------------
class ForkIn(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=120)
    change_summary: Optional[str] = Field(None, max_length=500)
    royalty_split_pct: int = Field(0, ge=0, le=50)


@router.post("/solutions/{solution_id}/fork", status_code=501)
async def fork_solution(
    solution_id: str, body: ForkIn,
    user: Dict[str, Any] = Depends(require_role("builder", "admin")),
) -> Dict[str, Any]:
    """Phase 9 stub. The full forking UX (lineage tracking, royalty split,
    deferred revenue accounting) is deferred. We still validate parent
    existence + lineage primitives so the contract is testable today.
    """
    db = get_db()
    parent = await db.solutions.find_one({"_id": solution_id})
    if not parent:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    # Surface the validated lineage we WOULD assign so the UX can preview it.
    raise HTTPException(
        status_code=501,
        detail={
            "error": "not_implemented_until_phase_9",
            "would_fork": {
                "parent_id": parent["_id"],
                "lineage_root_id": parent.get("lineage_root_id") or parent["_id"],
                "fork_depth": int(parent.get("fork_depth", 0)) + 1,
                "version": 1,
                "title": body.title or f"{parent.get('title','Solution')} (fork)",
                "change_summary": body.change_summary or "Initial fork",
                "royalty_split_pct": body.royalty_split_pct,
                "by_user_id": user["id"],
            },
        },
    )
