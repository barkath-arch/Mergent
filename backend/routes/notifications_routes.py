"""Notifications & preferences routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from db import get_db
from services.email import verify_unsubscribe_token
from services.notifications import DEFAULT_PREFS, get_prefs, unread_count

router = APIRouter(prefix="/api", tags=["notifications"])


class PrefsUpdate(BaseModel):
    channels: Optional[Dict[str, bool]] = None
    categories: Optional[Dict[str, Dict[str, bool]]] = None
    email_digest: Optional[str] = Field(None, pattern="^(realtime|daily|weekly|off)$")


class MarkReadIn(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=200)
    mark_all: bool = False


@router.get("/notifications")
async def list_notifications(
    user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
    only_unread: bool = False,
) -> Dict[str, Any]:
    db = get_db()
    q: Dict[str, Any] = {"user_id": user["id"]}
    if only_unread:
        q["read"] = False
    items: List[Dict[str, Any]] = []
    async for n in db.notifications.find(q).sort("created_at", -1).limit(limit):
        items.append({**n, "id": n.pop("_id")})
    return {
        "items": items,
        "count": len(items),
        "unread_total": await unread_count(user["id"]),
    }


@router.get("/notifications/unread-count")
async def get_unread(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"unread_total": await unread_count(user["id"])}


@router.post("/notifications/read")
async def mark_read(body: MarkReadIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    if body.mark_all:
        res = await db.notifications.update_many(
            {"user_id": user["id"], "read": False}, {"$set": {"read": True}},
        )
        return {"updated": res.modified_count, "unread_total": await unread_count(user["id"])}
    if not body.ids:
        return {"updated": 0, "unread_total": await unread_count(user["id"])}
    res = await db.notifications.update_many(
        {"_id": {"$in": body.ids}, "user_id": user["id"]}, {"$set": {"read": True}},
    )
    return {"updated": res.modified_count, "unread_total": await unread_count(user["id"])}


@router.get("/notification-preferences")
async def get_prefs_route(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return await get_prefs(user["id"])


@router.patch("/notification-preferences")
async def update_prefs(body: PrefsUpdate, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    update: Dict[str, Any] = {"_id": user["id"], "user_id": user["id"],
                              "updated_at": datetime.now(timezone.utc)}
    if body.channels is not None:
        update["channels"] = body.channels
    if body.categories is not None:
        # Merge with defaults so partial PATCH doesn't blow away unspecified keys.
        merged = {**DEFAULT_PREFS["categories"]}
        for k, v in body.categories.items():
            merged[k] = {**(merged.get(k) or {}), **v}
        update["categories"] = merged
    if body.email_digest is not None:
        update["email_digest"] = body.email_digest
    await db.notification_preferences.update_one(
        {"_id": user["id"]}, {"$set": update}, upsert=True,
    )
    return await get_prefs(user["id"])


@router.get("/notifications/unsubscribe")
async def unsubscribe(token: str) -> Dict[str, Any]:
    """Token-based one-click unsubscribe. Disables email for a category for a user.

    Returns a plain JSON so the email link works without a frontend session.
    """
    try:
        payload = verify_unsubscribe_token(token)
    except Exception:
        raise HTTPException(400, detail={"error": "invalid_token"})
    if payload.get("type") != "unsubscribe":
        raise HTTPException(400, detail={"error": "wrong_token_type"})

    user_id = payload.get("sub")
    category = payload.get("category", "")
    if not user_id or not category:
        raise HTTPException(400, detail={"error": "incomplete_token"})

    db = get_db()
    cur = await db.notification_preferences.find_one({"_id": user_id}) or {}
    categories = {**DEFAULT_PREFS["categories"], **(cur.get("categories") or {})}
    cur_cat = categories.get(category) or {"in_app": True, "email": True}
    cur_cat["email"] = False
    categories[category] = cur_cat
    await db.notification_preferences.update_one(
        {"_id": user_id},
        {"$set": {"user_id": user_id, "categories": categories,
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True, "category": category, "email_disabled_for_category": True}
