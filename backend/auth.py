"""MERGENT V1 auth core — JWT (access in body / refresh httpOnly cookie),
bcrypt password hashing, role-based dependency, brute-force throttle hooks,
Redis-backed refresh-token revocation.

Phase 1 amendment to the Phase-0 backend. Phase-0 routes remain unauthenticated
to keep the existing match-flow contract intact; new V1 surfaces (marketplace,
solutions, messaging, transactions, deployments) gate behind these dependencies.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status

from db import get_db

JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 15
REFRESH_TTL_DAYS = 7
REFRESH_COOKIE = "mergent_refresh"


def _jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=ACCESS_TTL_MIN),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Return (token, jti). jti is stored in Redis as the revocation key."""
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=REFRESH_TTL_DAYS),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM), jti


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])


# --------- Redis-backed refresh registry (SIMULATED: not durable across redis reboots) ---------
def _redis():
    import redis as redis_sync
    return redis_sync.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        socket_timeout=2, socket_connect_timeout=2, decode_responses=True,
    )


def register_refresh_jti(jti: str, user_id: str) -> None:
    try:
        _redis().setex(f"refresh:{jti}", REFRESH_TTL_DAYS * 86400, user_id)
    except Exception:
        pass  # Best-effort; token still has cryptographic exp.


def revoke_refresh_jti(jti: str) -> None:
    try:
        _redis().delete(f"refresh:{jti}")
    except Exception:
        pass


def refresh_jti_valid(jti: str) -> bool:
    try:
        return bool(_redis().exists(f"refresh:{jti}"))
    except Exception:
        return True  # Fail-open if Redis is down; token exp still binds.


# --------- FastAPI dependencies ---------
async def get_current_user(request: Request) -> Dict[str, Any]:
    # Header preferred (in-memory access token). Cookie fallback for legacy.
    token: Optional[str] = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("mergent_access")
    if not token:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "token_expired"})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail={"error": "invalid_token_type"})

    db = get_db()
    user = await db.users.find_one({"_id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail={"error": "user_not_found"})
    user["id"] = user.pop("_id")
    user.pop("password_hash", None)
    return user


def require_role(*allowed: str):
    async def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail={"error": "forbidden", "required": list(allowed)})
        return user
    return _dep


async def optional_user(request: Request) -> Optional[Dict[str, Any]]:
    """Soft-auth: return user if a valid token is present, else None.
    Used for endpoints that personalize results when logged in but stay public otherwise.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


# --------- Brute-force throttle (Mongo-backed sliding window) ---------
async def record_failed_login(identifier: str) -> int:
    db = get_db()
    now = _now()
    await db.login_attempts.update_one(
        {"_id": identifier},
        {"$push": {"timestamps": now}, "$set": {"updated_at": now}},
        upsert=True,
    )
    doc = await db.login_attempts.find_one({"_id": identifier})
    window_start = now - timedelta(minutes=15)
    recent = [t for t in (doc.get("timestamps") or []) if t and t > window_start]
    await db.login_attempts.update_one({"_id": identifier}, {"$set": {"timestamps": recent}})
    return len(recent)


async def clear_failed_logins(identifier: str) -> None:
    db = get_db()
    await db.login_attempts.delete_one({"_id": identifier})


async def is_locked_out(identifier: str, threshold: int = 5) -> bool:
    db = get_db()
    doc = await db.login_attempts.find_one({"_id": identifier})
    if not doc:
        return False
    window_start = _now() - timedelta(minutes=15)
    recent = [t for t in (doc.get("timestamps") or []) if t and t > window_start]
    return len(recent) >= threshold


def new_secure_token() -> str:
    return secrets.token_urlsafe(32)
