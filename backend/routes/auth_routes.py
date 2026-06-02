"""Auth routes — register / login / refresh / me / logout / forgot / reset.
SlowAPI rate limiting + brute-force counters + Redis refresh-jti registry.

Tokens:
  - access: returned in JSON body, frontend keeps in-memory + Authorization header
  - refresh: httpOnly cookie `mergent_refresh`, used by POST /refresh to mint new access
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from slowapi.util import get_remote_address

from auth import (
    REFRESH_COOKIE,
    REFRESH_TTL_DAYS,
    clear_failed_logins,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    is_locked_out,
    new_secure_token,
    record_failed_login,
    refresh_jti_valid,
    register_refresh_jti,
    revoke_refresh_jti,
    verify_password,
)
from db import get_db
from services.rate_limit import (
    forgot_limit as _forgot_limit,
    limiter,
    login_limit as _login_limit,
    register_limit as _register_limit,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------- Schemas ----------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern="^(buyer|builder)$")


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class VerifyIn(BaseModel):
    token: str


# ---------------------- Helpers ----------------------
def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TTL_DAYS * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


def _public_user(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc["_id"],
        "email": doc["email"],
        "name": doc.get("name"),
        "role": doc.get("role"),
        "avatar_url": doc.get("avatar_url"),
        "email_verified": bool(doc.get("email_verified")),
        "created_at": doc.get("created_at"),
    }


# ---------------------- Routes ----------------------
@router.post("/register", status_code=201, dependencies=[Depends(_register_limit())])
async def register(request: Request, response: Response, body: RegisterIn) -> Dict[str, Any]:
    db = get_db()
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(409, detail={"error": "email_taken"})
    user_id = new_secure_token()[:24]
    now = datetime.now(timezone.utc)
    doc = {
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(body.password),
        "name": body.name.strip(),
        "role": body.role,
        "avatar_url": None,
        "email_verified": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    # Seed empty profile row matching the role.
    if body.role == "builder":
        await db.builder_profiles.insert_one({
            "_id": user_id, "user_id": user_id, "headline": "", "bio": "",
            "skills": [], "rating": 0.0, "review_count": 0,
            "solutions_count": 0, "deployments_count": 0, "earnings_usd": 0.0,
            "joined_at": now, "verified": False,
        })
    else:
        await db.buyer_profiles.insert_one({
            "_id": user_id, "user_id": user_id, "company": "", "industry": "",
            "purchases_count": 0, "spend_usd": 0.0, "joined_at": now,
        })

    # Email verification token (sent via Resend, falls back to console log).
    verify_token = new_secure_token()
    await db.email_verification_tokens.insert_one({
        "_id": verify_token, "user_id": user_id,
        "expires_at": now + timedelta(hours=24), "used": False,
    })
    try:
        from services.email import send_email
        await send_email(
            to=email, template_name="email_verify",
            context={"name": body.name.strip(), "token": verify_token},
            user_id=user_id, category="system",
        )
    except Exception as e:
        print(f"[mergent.auth] verify_email_fallback user={email} link=/auth/verify?token={verify_token} err={e}")

    access = create_access_token(user_id, email, body.role)
    refresh, jti = create_refresh_token(user_id)
    register_refresh_jti(jti, user_id)
    _set_refresh_cookie(response, refresh)
    return {"user": _public_user(doc), "access_token": access, "token_type": "bearer"}


@router.post("/login", dependencies=[Depends(_login_limit())])
async def login(request: Request, response: Response, body: LoginIn) -> Dict[str, Any]:
    db = get_db()
    email = body.email.lower().strip()
    ip = get_remote_address(request)
    identifier = f"{ip}:{email}"

    if await is_locked_out(identifier):
        raise HTTPException(429, detail={"error": "locked_out", "retry_after_min": 15})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await record_failed_login(identifier)
        raise HTTPException(401, detail={"error": "invalid_credentials"})

    await clear_failed_logins(identifier)
    access = create_access_token(user["_id"], email, user["role"])
    refresh, jti = create_refresh_token(user["_id"])
    register_refresh_jti(jti, user["_id"])
    _set_refresh_cookie(response, refresh)
    return {"user": _public_user(user), "access_token": access, "token_type": "bearer"}


@router.post("/refresh")
async def refresh(response: Response, mergent_refresh: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    if not mergent_refresh:
        raise HTTPException(401, detail={"error": "no_refresh_cookie"})
    try:
        payload = decode_token(mergent_refresh)
    except Exception:
        raise HTTPException(401, detail={"error": "invalid_refresh"})
    if payload.get("type") != "refresh":
        raise HTTPException(401, detail={"error": "wrong_token_type"})
    jti = payload.get("jti", "")
    if not refresh_jti_valid(jti):
        raise HTTPException(401, detail={"error": "refresh_revoked"})

    db = get_db()
    user = await db.users.find_one({"_id": payload["sub"]})
    if not user:
        raise HTTPException(401, detail={"error": "user_not_found"})
    access = create_access_token(user["_id"], user["email"], user["role"])
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
async def logout(response: Response, mergent_refresh: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    if mergent_refresh:
        try:
            payload = decode_token(mergent_refresh)
            if payload.get("type") == "refresh":
                revoke_refresh_jti(payload.get("jti", ""))
        except Exception:
            pass
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me")
async def me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return user


@router.post("/verify-email")
async def verify_email(body: VerifyIn) -> Dict[str, Any]:
    db = get_db()
    tok = await db.email_verification_tokens.find_one({"_id": body.token})
    if not tok or tok.get("used"):
        raise HTTPException(400, detail={"error": "invalid_or_used_token"})
    if tok["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(400, detail={"error": "token_expired"})
    await db.users.update_one({"_id": tok["user_id"]}, {"$set": {"email_verified": True}})
    await db.email_verification_tokens.update_one({"_id": body.token}, {"$set": {"used": True}})
    return {"ok": True}


@router.post("/forgot-password", dependencies=[Depends(_forgot_limit())])
async def forgot(request: Request, body: ForgotIn) -> Dict[str, Any]:
    db = get_db()
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if user:
        token = new_secure_token()
        await db.password_reset_tokens.insert_one({
            "_id": token, "user_id": user["_id"],
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "used": False,
        })
        try:
            from services.email import send_email
            await send_email(
                to=email, template_name="password_reset",
                context={"email": email, "token": token},
                user_id=user["_id"], category="system",
            )
        except Exception as e:
            print(f"[mergent.auth] password_reset_fallback user={email} link=/auth/reset?token={token} err={e}")
    # Always 200 to avoid email enumeration.
    return {"ok": True}


@router.post("/reset-password")
async def reset(body: ResetIn) -> Dict[str, Any]:
    db = get_db()
    tok = await db.password_reset_tokens.find_one({"_id": body.token})
    if not tok or tok.get("used"):
        raise HTTPException(400, detail={"error": "invalid_or_used_token"})
    if tok["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(400, detail={"error": "token_expired"})
    await db.users.update_one(
        {"_id": tok["user_id"]},
        {"$set": {"password_hash": hash_password(body.password), "updated_at": datetime.now(timezone.utc)}},
    )
    await db.password_reset_tokens.update_one({"_id": body.token}, {"$set": {"used": True}})
    return {"ok": True}


@router.get("/google/status")
async def google_status() -> Dict[str, Any]:
    enabled = os.environ.get("ENABLE_GOOGLE_AUTH", "false").lower() == "true"
    return {"enabled": enabled}
