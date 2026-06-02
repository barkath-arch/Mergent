"""Notifications service — creates docs + pushes WS + schedules emails.

Honors per-user notification_preferences.
Email debounce uses a Redis SETNX key per (user_id, debounce_key) with 300s TTL.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from db import get_db
from services.email import send_email
from services.ws_v1 import get_v1_ws

logger = logging.getLogger("services.notifications")

DEFAULT_PREFS = {
    "channels": {"in_app": True, "email": True, "push": True},
    "categories": {
        "messages": {"in_app": True, "email": True},
        "transactions": {"in_app": True, "email": True},
        "deployments": {"in_app": True, "email": True},
        "reviews": {"in_app": True, "email": True},
        "match": {"in_app": True, "email": False},
        "system": {"in_app": True, "email": True},
    },
    "email_digest": "realtime",
}


async def get_prefs(user_id: str) -> Dict[str, Any]:
    db = get_db()
    p = await db.notification_preferences.find_one({"_id": user_id})
    if not p:
        return DEFAULT_PREFS
    out = {**DEFAULT_PREFS, **{k: v for k, v in p.items() if k != "_id"}}
    out["categories"] = {**DEFAULT_PREFS["categories"], **(p.get("categories") or {})}
    out["channels"] = {**DEFAULT_PREFS["channels"], **(p.get("channels") or {})}
    return out


def _redis():
    import redis as redis_sync
    return redis_sync.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
    )


def _email_debounce_ok(user_id: str, key: str, ttl_s: int = 300) -> bool:
    try:
        return bool(_redis().set(f"email_debounce:{user_id}:{key}", "1", ex=ttl_s, nx=True))
    except Exception:
        return True


async def notify(
    user_id: str,
    *,
    type: str,
    category: str,
    title: str,
    body: str,
    link: Optional[str] = None,
    email_template: Optional[str] = None,
    email_context: Optional[Dict[str, Any]] = None,
    debounce_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Create notification + WS push + optional email.

    `category` ∈ {messages, transactions, deployments, reviews, match, system}.
    Returns {created, ws_sent, email_result}.
    """
    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return {"created": False, "reason": "user_not_found"}
    prefs = await get_prefs(user_id)
    cat_prefs = prefs["categories"].get(category, {"in_app": True, "email": False})

    created = False
    nid = None
    if cat_prefs.get("in_app", True) and prefs["channels"].get("in_app", True):
        nid = str(uuid.uuid4())
        doc = {
            "_id": nid, "user_id": user_id, "type": type, "category": category,
            "title": title, "body": body, "link": link, "read": False,
            "debounce_key": debounce_key,
            "created_at": datetime.now(timezone.utc),
        }
        await db.notifications.insert_one(doc)
        created = True
        # WS push
        try:
            await get_v1_ws().broadcast("conversations", user_id, {
                "type": "notification", "notification": {**doc, "id": nid, "_id": None},
            })
        except Exception:
            pass

    email_result: Optional[Dict[str, Any]] = None
    wants_email = cat_prefs.get("email", False) and prefs["channels"].get("email", True)
    if email_template and wants_email:
        dbk = debounce_key or f"{type}:{(link or '')[:64]}"
        if _email_debounce_ok(user_id, dbk):
            email_result = await send_email(
                to=user["email"],
                template_name=email_template,
                context={**(email_context or {}), "name": user.get("name", "")},
                category=category,
                user_id=user_id,
            )
        else:
            email_result = {"sent": False, "reason": "debounced"}

    return {"created": created, "notification_id": nid, "email_result": email_result}


async def unread_count(user_id: str) -> int:
    db = get_db()
    return await db.notifications.count_documents({"user_id": user_id, "read": False})
