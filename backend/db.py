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

    def _swallow(label: str):
        """Decorator-ish: log & ignore IndexAlreadyExists style failures."""
        async def _wrap(coro):
            try:
                await coro
            except Exception as exc:
                logger.warning("index_create_failed", extra={"index": label, "error": str(exc)})
        return _wrap

    # solutions (existing)
    await _swallow("solutions_text")(db.solutions.create_index(
        [("title", "text"), ("description", "text"), ("tags", "text")],
        name="solutions_text_idx",
        default_language="english",
        background=True,
    ))
    await _swallow("solutions_category")(db.solutions.create_index("category", name="solutions_category_idx", background=True))
    await _swallow("solutions_title_unique")(db.solutions.create_index("title", unique=True, name="solutions_title_unique", background=True))

    # ------------------------------------------------------------------ #
    # Phase AGENTS Step 1: collection rename `orchestration_runs` -> `match_runs`.
    # One-time copy if match_runs is empty AND the legacy collection exists.
    # The legacy collection is NOT dropped (kept for safety / rollback).
    # ------------------------------------------------------------------ #
    try:
        match_count = await db.match_runs.estimated_document_count()
        if match_count == 0:
            existing_collections = await db.list_collection_names()
            if "orchestration_runs" in existing_collections:
                legacy_count = await db.orchestration_runs.estimated_document_count()
                if legacy_count > 0:
                    docs = [d async for d in db.orchestration_runs.find({})]
                    if docs:
                        await db.match_runs.insert_many(docs, ordered=False)
                        logger.info("match_runs_migrated", extra={"copied": len(docs)})
    except Exception as exc:
        logger.warning("match_runs_migration_failed", extra={"error": str(exc)})

    # match_runs indexes (the new canonical collection)
    await _swallow("runs_created")(db.match_runs.create_index("created_at", name="runs_created_idx", background=True))
    await _swallow("runs_buyer_created")(db.match_runs.create_index(
        [("buyer_id", 1), ("created_at", -1)], name="runs_buyer_created_idx", background=True,
    ))

    # ai_usage_logs (Phase AGENTS Step 1)
    await _swallow("ai_usage_agent_created")(db.ai_usage_logs.create_index(
        [("agent_name", 1), ("created_at", -1)], name="ai_usage_agent_created_idx", background=True,
    ))
    await _swallow("ai_usage_ttl")(db.ai_usage_logs.create_index(
        "created_at", name="ai_usage_ttl", expireAfterSeconds=2592000, background=True,
    ))

    # agent_runs (Phase AGENTS Step 1)
    await _swallow("agent_runs_agent_created")(db.agent_runs.create_index(
        [("agent_name", 1), ("created_at", -1)], name="agent_runs_agent_created_idx", background=True,
    ))
    await _swallow("agent_runs_run_id")(db.agent_runs.create_index(
        "run_id", name="agent_runs_run_id_idx", background=True,
    ))
    await _swallow("agent_runs_ttl")(db.agent_runs.create_index(
        "created_at", name="agent_runs_ttl", expireAfterSeconds=2592000, background=True,
    ))

    # Phase R additions
    await _swallow("users_email_unique")(db.users.create_index("email", unique=True, name="users_email_unique", background=True))
    await _swallow("ev_tokens_ttl")(db.email_verification_tokens.create_index(
        "expires_at", name="ev_tokens_ttl", expireAfterSeconds=0, background=True,
    ))
    await _swallow("pw_reset_tokens_ttl")(db.password_reset_tokens.create_index(
        "expires_at", name="pw_reset_tokens_ttl", expireAfterSeconds=0, background=True,
    ))
    await _swallow("conv_participants")(db.conversations.create_index("participants", name="conv_participants_idx", background=True))
    await _swallow("messages_conv_ts")(db.messages.create_index(
        [("conversation_id", 1), ("created_at", 1)], name="messages_conv_ts_idx", background=True,
    ))
    await _swallow("notif_user_read_ts")(db.notifications.create_index(
        [("user_id", 1), ("read", 1), ("created_at", -1)], name="notif_user_read_ts_idx", background=True,
    ))
    await _swallow("saved_user_sol_unique")(db.saved_items.create_index(
        [("user_id", 1), ("solution_id", 1)], unique=True, name="saved_user_sol_unique", background=True,
    ))
    await _swallow("reviews_solution")(db.reviews.create_index("solution_id", name="reviews_solution_idx", background=True))
    await _swallow("reviews_builder")(db.reviews.create_index("builder_id", name="reviews_builder_idx", background=True))
    await _swallow("tx_buyer")(db.transactions.create_index("buyer_id", name="tx_buyer_idx", background=True))
    await _swallow("tx_builder")(db.transactions.create_index("builder_id", name="tx_builder_idx", background=True))
    await _swallow("login_attempts_ttl")(db.login_attempts.create_index(
        "updated_at", name="login_attempts_ttl", expireAfterSeconds=900, background=True,
    ))

    logger.info("mongo_indexes_ensured")
