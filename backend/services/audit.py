"""Production-grade audit log + minimal in-process rate-limit helpers.

write_audit() is fire-and-forget (await but errors swallowed) so handlers never
fail because audit is down. The collection has a TTL of 365 days.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from db import get_db

logger = logging.getLogger("services.audit")


async def write_audit(
    actor_user_id: Optional[str],
    actor_role: Optional[str],
    action: str,
    target_collection: Optional[str] = None,
    target_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    db = get_db()
    aid = str(uuid.uuid4())
    doc = {
        "_id": aid,
        "ts": datetime.now(timezone.utc),
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "action": action,
        "target_collection": target_collection,
        "target_id": target_id,
        "before": before,
        "after": after,
        "ip": ip,
        "user_agent": user_agent,
        "request_id": request_id,
        "metadata": metadata or {},
    }
    try:
        await db.audit_log.insert_one(doc)
    except Exception as e:
        logger.warning(f"audit_write_failed action={action} err={e}")
    return aid
