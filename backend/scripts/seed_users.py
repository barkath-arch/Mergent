"""Phase R — idempotent seed for 3 test users (buyer / builder / admin).

Run:
    cd /app/backend
    python -m scripts.seed_users

Skips any account whose email already exists. Also seeds matching
`builder_profiles` / `buyer_profiles` rows so role-aware endpoints work.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

from auth import hash_password  # noqa: E402


USERS: List[Dict[str, Any]] = [
    {
        "email": "buyer@example.com",
        "password": "buyer123!",
        "name": "Bea Buyer",
        "role": "buyer",
    },
    {
        "email": "builder@example.com",
        "password": "builder123!",
        "name": "Bo Builder",
        "role": "builder",
    },
    {
        "email": "admin@example.com",
        "password": "admin123!",
        "name": "Ada Admin",
        "role": "admin",
    },
]


async def _seed_one(db, u: Dict[str, Any]) -> Dict[str, Any]:
    email = u["email"].lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        return {"email": email, "action": "skipped", "id": existing["_id"]}

    uid = uuid.uuid4().hex[:24]
    now = datetime.now(timezone.utc)
    user_doc = {
        "_id": uid,
        "email": email,
        "password_hash": hash_password(u["password"]),
        "name": u["name"],
        "role": u["role"],
        "avatar_url": None,
        "email_verified": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)

    if u["role"] == "builder":
        await db.builder_profiles.update_one(
            {"_id": uid},
            {"$set": {
                "_id": uid, "user_id": uid,
                "headline": "Seed builder for tests", "bio": "",
                "skills": ["FastAPI", "React", "MongoDB"],
                "rating": 0.0, "review_count": 0,
                "solutions_count": 0, "deployments_count": 0, "earnings_usd": 0.0,
                "joined_at": now, "verified": True,
            }},
            upsert=True,
        )
    else:
        # admin gets a buyer-shaped row too for /me PATCH compatibility.
        await db.buyer_profiles.update_one(
            {"_id": uid},
            {"$set": {
                "_id": uid, "user_id": uid,
                "company": "Mergent QA", "industry": "Software",
                "purchases_count": 0, "spend_usd": 0.0, "joined_at": now,
            }},
            upsert=True,
        )

    return {"email": email, "action": "inserted", "id": uid, "role": u["role"]}


async def main() -> List[Dict[str, Any]]:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = client[os.environ["DB_NAME"]]
    try:
        # Ensure unique email index exists before we attempt inserts.
        try:
            await db.users.create_index("email", unique=True, name="users_email_unique", background=True)
        except Exception:
            pass
        out: List[Dict[str, Any]] = []
        for u in USERS:
            out.append(await _seed_one(db, u))
        return out
    finally:
        client.close()


if __name__ == "__main__":
    res = asyncio.run(main())
    for r in res:
        print(f"[seed_users] {r}")
    print("[seed_users] done.")
