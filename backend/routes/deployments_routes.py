"""Deployment FSM — 7 step state machine with WS log streaming.

# SIMULATED: real state machine, simulated infra
Steps execute as async background sleeps producing fake log lines.
States: created → provisioning → configuring → installing → smoke_testing → healthchecking → live
With branches: failed (from any), rolling_back, redeploying.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from auth import decode_token, get_current_user
from db import get_db
from services.ws_v1 import get_v1_ws

router = APIRouter(prefix="/api", tags=["deployments"])

STEPS = [
    ("provisioning", "Provisioning compute & network"),
    ("configuring", "Configuring environment & secrets"),
    ("installing", "Installing dependencies & seeding data"),
    ("smoke_testing", "Running smoke tests"),
    ("healthchecking", "Running health checks"),
    ("finalizing", "Routing traffic & promoting version"),
    ("live", "Deployment live"),
]


class StartDeploymentIn(BaseModel):
    solution_id: str
    transaction_id: Optional[str] = None
    environment: str = "production"


class ActionIn(BaseModel):
    action: str  # rollback | redeploy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {**d}
    out["id"] = out.pop("_id")
    return out


async def _emit_log(deployment_id: str, level: str, msg: str) -> None:
    ws = get_v1_ws()
    db = get_db()
    log_entry = {"ts": _now().isoformat(), "level": level, "msg": msg}
    await db.deployments.update_one({"_id": deployment_id}, {"$push": {"logs": log_entry}})
    await ws.broadcast("deployments", deployment_id, {"type": "log", **log_entry})


async def _set_state(deployment_id: str, state: str, version: Optional[str] = None) -> None:
    db = get_db()
    update: Dict[str, Any] = {"status": state, "updated_at": _now()}
    if version:
        update["current_version"] = version
    await db.deployments.update_one(
        {"_id": deployment_id},
        {"$set": update,
         "$push": {"state_history": {"state": state, "at": _now()}}},
    )
    await get_v1_ws().broadcast("deployments", deployment_id, {
        "type": "state", "state": state, "ts": _now().isoformat(),
    })
    # Notify owner on milestone states (Phase 7).
    if state in ("live", "failed", "rolling_back"):
        try:
            from services.notifications import notify
            d = await db.deployments.find_one({"_id": deployment_id})
            if d:
                await notify(
                    d.get("owner_id"),
                    type="deployment_status",
                    category="deployments",
                    title=f"Deployment {state.replace('_',' ')}",
                    body=f"{d.get('solution_title','Your deployment')} is now {state}.",
                    link=f"/deployments/{deployment_id}",
                    email_template="deployment_status",
                    email_context={
                        "deployment_id": deployment_id,
                        "solution_title": d.get("solution_title"),
                        "state": state,
                        "version": d.get("current_version"),
                    },
                    debounce_key=f"dep:{deployment_id}:{state}",
                )
        except Exception as e:
            print(f"[mergent.dep] notify_failed: {e}")


async def _run_deployment(deployment_id: str, version: str) -> None:
    try:
        await _emit_log(deployment_id, "info", f"Starting deployment {deployment_id[:8]} (version={version})")
        for state, label in STEPS:
            await _set_state(deployment_id, state)
            await _emit_log(deployment_id, "info", label)
            # Simulated work — 0.8-1.6s per step
            await asyncio.sleep(0.8 + random.random() * 0.8)
            if state == "smoke_testing":
                await _emit_log(deployment_id, "info", "  PASS health endpoint")
                await _emit_log(deployment_id, "info", "  PASS api smoke")
            if state == "healthchecking":
                await _emit_log(deployment_id, "info", "  uptime=100% latency_p95=142ms")
        await _emit_log(deployment_id, "ok", f"Deployment live at https://app-{deployment_id[:8]}.mergent.preview")
        await get_v1_ws().broadcast("deployments", deployment_id, {
            "type": "completed", "ts": _now().isoformat(),
        })
        db = get_db()
        # Bump builder deployment counter
        d = await db.deployments.find_one({"_id": deployment_id})
        if d:
            await db.builder_profiles.update_one(
                {"_id": d["builder_id"]}, {"$inc": {"deployments_count": 1}}
            )
    except Exception as e:
        await _set_state(deployment_id, "failed")
        await _emit_log(deployment_id, "error", f"Deployment failed: {e}")


@router.post("/deployments", status_code=201)
async def start_deployment(body: StartDeploymentIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    sol = await db.solutions.find_one({"_id": body.solution_id})
    if not sol:
        raise HTTPException(404, detail={"error": "solution_not_found"})
    did = str(uuid.uuid4())
    now = _now()
    version = f"v{int(now.timestamp())}"
    doc = {
        "_id": did,
        "solution_id": body.solution_id,
        "solution_title": sol.get("title"),
        "builder_id": sol["builder_id"],
        "owner_id": user["id"],
        "transaction_id": body.transaction_id,
        "environment": body.environment,
        "current_version": version,
        "versions": [{"version": version, "deployed_at": now, "state": "starting"}],
        "status": "created",
        "logs": [],
        "state_history": [{"state": "created", "at": now}],
        "simulated_infra": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.deployments.insert_one(doc)
    asyncio.create_task(_run_deployment(did, version))
    return _serialize(doc)


@router.get("/deployments")
async def list_my_deployments(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    q = {"$or": [{"owner_id": user["id"]}, {"builder_id": user["id"]}]}
    items = [_serialize(d) async for d in db.deployments.find(q).sort("created_at", -1).limit(50)]
    return {"items": items, "count": len(items)}


@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    d = await db.deployments.find_one({"_id": deployment_id})
    if not d:
        raise HTTPException(404, detail={"error": "deployment_not_found"})
    if user["id"] not in (d["owner_id"], d["builder_id"]) and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_authorized"})
    return _serialize(d)


@router.post("/deployments/{deployment_id}/action")
async def deployment_action(deployment_id: str, body: ActionIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    d = await db.deployments.find_one({"_id": deployment_id})
    if not d:
        raise HTTPException(404, detail={"error": "deployment_not_found"})
    if user["id"] not in (d["owner_id"], d["builder_id"]) and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_authorized"})

    if body.action == "rollback":
        if len(d.get("versions", [])) < 2:
            raise HTTPException(409, detail={"error": "no_prior_version"})
        prev = d["versions"][-2]["version"]
        await _set_state(deployment_id, "rolling_back")
        await _emit_log(deployment_id, "warn", f"Rolling back to {prev}")
        await asyncio.sleep(0.6)
        await _set_state(deployment_id, "live", version=prev)
        await _emit_log(deployment_id, "ok", f"Rolled back to {prev}")
        return _serialize(await db.deployments.find_one({"_id": deployment_id}))

    if body.action == "redeploy":
        new_version = f"v{int(_now().timestamp())}"
        await db.deployments.update_one(
            {"_id": deployment_id},
            {"$push": {"versions": {"version": new_version, "deployed_at": _now(), "state": "starting"}}},
        )
        asyncio.create_task(_run_deployment(deployment_id, new_version))
        return _serialize(await db.deployments.find_one({"_id": deployment_id}))

    raise HTTPException(400, detail={"error": "unknown_action"})


# ----- WebSocket -----
async def _ws_auth(ws: WebSocket) -> Optional[str]:
    token = ws.query_params.get("token", "")
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except Exception:
        return None


def register_ws(app) -> None:
    @app.websocket("/api/ws/deployments/{deployment_id}")
    async def dep_ws(websocket: WebSocket, deployment_id: str) -> None:
        user_id = await _ws_auth(websocket)
        if not user_id:
            await websocket.close(code=4401)
            return
        db = get_db()
        d = await db.deployments.find_one({"_id": deployment_id})
        if not d or user_id not in (d.get("owner_id"), d.get("builder_id")):
            await websocket.close(code=4403)
            return
        ws = get_v1_ws()
        await ws.connect("deployments", deployment_id, websocket)
        try:
            # Replay existing logs
            for log in (d.get("logs") or []):
                await websocket.send_json({"type": "log", **log})
            await websocket.send_json({"type": "state", "state": d.get("status"), "ts": _now().isoformat()})
            while True:
                msg = await websocket.receive_text()
                if msg.strip().lower() == "ping":
                    await websocket.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await ws.disconnect("deployments", deployment_id, websocket)
