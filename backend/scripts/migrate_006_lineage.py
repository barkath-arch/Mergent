"""Migration 006 — forking-aware schema.

Adds lineage/fork primitives to every doc that the forking UX (Phase 9) will
operate on. Idempotent — re-running is a no-op for already-migrated docs.

Run: `python3 scripts/migrate_006_lineage.py`
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from db import get_db, ensure_indexes  # noqa: E402


async def main() -> None:
    db = get_db()
    await ensure_indexes()
    now = datetime.now(timezone.utc)

    # ----- solutions ----------------------------------------------------------
    solutions_updated = 0
    async for sol in db.solutions.find({}, {"_id": 1, "lineage_root_id": 1}):
        if sol.get("lineage_root_id"):
            continue
        await db.solutions.update_one(
            {"_id": sol["_id"]},
            {"$set": {
                "parent_id": None,
                "lineage_root_id": sol["_id"],
                "fork_depth": 0,
                "fork_children_count": 0,
                "is_fork": False,
                "version": 1,
                "version_history": [{
                    "version": 1,
                    "changed_by": "system:migration_006",
                    "changed_at": now,
                    "change_summary": "initial seed (lineage backfilled)",
                    "snapshot_inline": None,
                }],
                "royalty_split_pct": 0,
            }},
        )
        solutions_updated += 1
    print(f"[migration_006] solutions backfilled: {solutions_updated}")

    # ----- transactions -------------------------------------------------------
    tx_updated = await db.transactions.update_many(
        {"forked_from_solution_id": {"$exists": False}},
        {"$set": {"forked_from_solution_id": None}},
    )
    print(f"[migration_006] transactions backfilled: {tx_updated.modified_count}")

    # ----- deployments --------------------------------------------------------
    dep_updated = 0
    async for d in db.deployments.find({}, {"_id": 1, "solution_id": 1, "source_version": 1, "lineage_root_id": 1}):
        if d.get("source_version") is not None and d.get("lineage_root_id"):
            continue
        sol = await db.solutions.find_one({"_id": d.get("solution_id")}, {"version": 1, "lineage_root_id": 1})
        await db.deployments.update_one(
            {"_id": d["_id"]},
            {"$set": {
                "source_version": (sol or {}).get("version", 1),
                "lineage_root_id": (sol or {}).get("lineage_root_id"),
            }},
        )
        dep_updated += 1
    print(f"[migration_006] deployments backfilled: {dep_updated}")

    # ----- indexes ------------------------------------------------------------
    await db.solutions.create_index([("lineage_root_id", 1), ("fork_depth", 1)])
    await db.solutions.create_index([("parent_id", 1)])
    print("[migration_006] lineage indexes ensured")
    print("[migration_006] DONE")


if __name__ == "__main__":
    asyncio.run(main())
