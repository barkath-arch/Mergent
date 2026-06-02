"""MongoDB / motor connection + retry helpers."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from services.logging_config import get_logger

logger = get_logger(__name__)


_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(
            os.environ["MONGO_URL"],
            serverSelectionTimeoutMS=5000,
            retryWrites=True,
        )
        _db = _client[os.environ["DB_NAME"]]
    return _db


def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


async def with_retry(coro_factory, attempts: int = 2, base_delay: float = 0.3) -> Any:
    """Wrap a (no-arg) coroutine factory with a single-retry helper."""
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            last = exc
            logger.warning("db_op_failed", extra={"attempt": i, "error": str(exc)})
            await asyncio.sleep(base_delay * (i + 1))
    assert last is not None
    raise last


async def ensure_indexes() -> None:
    db = get_db()
    await db.solutions.create_index(
        [("title", "text"), ("description", "text"), ("tags", "text")],
        name="solutions_text_idx",
        default_language="english",
    )
    await db.solutions.create_index("category", name="solutions_category_idx")
    await db.solutions.create_index("title", unique=True, name="solutions_title_unique")
    await db.orchestration_runs.create_index("created_at", name="runs_created_idx")
    logger.info("mongo_indexes_ensured")
