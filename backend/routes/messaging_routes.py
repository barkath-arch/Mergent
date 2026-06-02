"""Messaging — conversations + REST send + WS stream for unread/typing/new_message.
Topbar unread badge driven by WS `unread_count` events.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from auth import decode_token, get_current_user
from db import get_db
from services.ws_v1 import get_v1_ws

router = APIRouter(prefix="/api", tags=["messaging"])


class StartConversationIn(BaseModel):
    recipient_id: str
    initial_message: Optional[str] = Field(None, max_length=4000)


class SendMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class TypingIn(BaseModel):
    is_typing: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_conv(db, conv_id: str, user_id: str) -> Dict[str, Any]:
    conv = await db.conversations.find_one({"_id": conv_id})
    if not conv or user_id not in conv.get("participants", []):
        raise HTTPException(404, detail={"error": "conversation_not_found"})
    return conv


async def _unread_for(db, user_id: str) -> int:
    pipeline = [
        {"$match": {"participants": user_id}},
        {"$project": {"unread": {"$ifNull": [f"$unread.{user_id}", 0]}}},
        {"$group": {"_id": None, "total": {"$sum": "$unread"}}},
    ]
    async for row in db.conversations.aggregate(pipeline):
        return int(row.get("total", 0))
    return 0


@router.post("/conversations", status_code=201)
async def start_conversation(body: StartConversationIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if body.recipient_id == user["id"]:
        raise HTTPException(400, detail={"error": "cannot_message_self"})
    db = get_db()
    recipient = await db.users.find_one({"_id": body.recipient_id})
    if not recipient:
        raise HTTPException(404, detail={"error": "recipient_not_found"})
    participants = sorted([user["id"], body.recipient_id])
    existing = await db.conversations.find_one({"participants": participants})
    if existing:
        return {**existing, "id": existing.pop("_id")}
    conv_id = str(uuid.uuid4())
    now = _now()
    doc = {
        "_id": conv_id,
        "participants": participants,
        "participant_names": {user["id"]: user.get("name"), body.recipient_id: recipient.get("name")},
        "participant_avatars": {user["id"]: user.get("avatar_url"), body.recipient_id: recipient.get("avatar_url")},
        "last_message": None,
        "last_message_at": now,
        "unread": {p: 0 for p in participants},
        "created_at": now,
    }
    await db.conversations.insert_one(doc)
    if body.initial_message:
        await _store_message(db, conv_id, user["id"], body.initial_message, participants)
    return {**doc, "id": doc.pop("_id")}


@router.get("/conversations")
async def list_conversations(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    cursor = db.conversations.find({"participants": user["id"]}).sort("last_message_at", -1).limit(50)
    items = []
    async for c in cursor:
        items.append({
            **c, "id": c.pop("_id"),
            "unread_for_me": int(c.get("unread", {}).get(user["id"], 0)),
        })
    return {"items": items, "count": len(items), "total_unread": await _unread_for(db, user["id"])}


@router.get("/conversations/{conv_id}/messages")
async def list_messages(conv_id: str, limit: int = Query(50, ge=1, le=200), user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    await _resolve_conv(db, conv_id, user["id"])
    cursor = db.messages.find({"conversation_id": conv_id}).sort("created_at", 1).limit(limit)
    items = [{**m, "id": m.pop("_id")} async for m in cursor]
    # mark as read for me
    await db.conversations.update_one({"_id": conv_id}, {"$set": {f"unread.{user['id']}": 0}})
    await get_v1_ws().broadcast("conversations", user["id"], {
        "type": "unread_count", "total_unread": await _unread_for(db, user["id"]),
    })
    return {"items": items, "count": len(items)}


async def _store_message(db, conv_id: str, sender_id: str, text: str, participants: List[str]) -> Dict[str, Any]:
    mid = str(uuid.uuid4())
    now = _now()
    msg = {
        "_id": mid, "conversation_id": conv_id, "sender_id": sender_id,
        "text": text, "created_at": now, "read_by": [sender_id],
    }
    await db.messages.insert_one(msg)
    inc = {f"unread.{p}": 1 for p in participants if p != sender_id}
    await db.conversations.update_one(
        {"_id": conv_id},
        {"$set": {"last_message": text[:200], "last_message_at": now, f"unread.{sender_id}": 0}, "$inc": inc},
    )
    ws = get_v1_ws()
    payload = {"type": "new_message", "conversation_id": conv_id, "message": {**msg, "id": mid}}
    sender = await db.users.find_one({"_id": sender_id}) or {}
    sender_name = sender.get("name") or "Someone"
    for p in participants:
        await ws.broadcast("conversations", p, payload)
        await ws.broadcast("conversations", p, {"type": "unread_count", "total_unread": await _unread_for(db, p)})
        if p != sender_id:
            # Email + in-app notification with 5-minute debounce per conversation.
            try:
                from services.notifications import notify
                await notify(
                    p, type="new_message", category="messages",
                    title=f"New message from {sender_name}",
                    body=text[:280],
                    link=f"/messages?c={conv_id}",
                    email_template="new_message",
                    email_context={"sender_name": sender_name, "message_preview": text,
                                    "conversation_id": conv_id},
                    debounce_key=f"msg:{conv_id}",
                )
            except Exception as e:
                print(f"[mergent.msg] notify_failed: {e}")
    return {**msg, "id": mid}


@router.post("/conversations/{conv_id}/messages", status_code=201)
async def send_message(conv_id: str, body: SendMessageIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    conv = await _resolve_conv(db, conv_id, user["id"])
    return await _store_message(db, conv_id, user["id"], body.text.strip(), conv["participants"])


@router.post("/conversations/{conv_id}/typing")
async def typing(conv_id: str, body: TypingIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    conv = await _resolve_conv(db, conv_id, user["id"])
    ws = get_v1_ws()
    for p in conv["participants"]:
        if p == user["id"]:
            continue
        await ws.broadcast("conversations", p, {
            "type": "typing", "conversation_id": conv_id,
            "user_id": user["id"], "is_typing": body.is_typing,
        })
    return {"ok": True}


@router.get("/messaging/unread-count")
async def my_unread(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    return {"total_unread": await _unread_for(db, user["id"])}


# ----- WebSocket -----
async def _ws_auth_user_id(websocket: WebSocket) -> Optional[str]:
    """Authenticate WS via ?token=... access token. Returns user_id or None."""
    token = websocket.query_params.get("token", "")
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except Exception:
        return None


def register_ws(app) -> None:  # called from server.py
    @app.websocket("/api/ws/conversations/{user_id}")
    async def conv_ws(websocket: WebSocket, user_id: str) -> None:
        authed_uid = await _ws_auth_user_id(websocket)
        if authed_uid != user_id:
            await websocket.close(code=4401)
            return
        ws = get_v1_ws()
        await ws.connect("conversations", user_id, websocket)
        db = get_db()
        try:
            # Push initial unread snapshot
            await websocket.send_json({"type": "unread_count", "total_unread": await _unread_for(db, user_id)})
            while True:
                msg = await websocket.receive_text()
                if msg.strip().lower() == "ping":
                    await websocket.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await ws.disconnect("conversations", user_id, websocket)
