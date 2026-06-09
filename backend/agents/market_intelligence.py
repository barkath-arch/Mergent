"""MarketIntelligenceAgent — aggregates marketplace trends from analytics_events.

Runs on a Celery beat schedule (every 6 hours). Does NOT run per-request.
Stores result in market_intelligence_cache collection.
Exposed via GET /api/market/intelligence.

No LLM call — pure aggregation. Extends BaseAgent for observability.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from agents.base import BaseAgent
from db import get_db


class MarketIntelligenceAgent(BaseAgent):
    agent_name = "MarketIntelligenceAgent"
    agent_version = "1.0.0"

    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002
        db = get_db()
        since = datetime.now(timezone.utc) - timedelta(days=30)

        # Trending categories from solution views
        category_cursor = db.analytics_events.aggregate([
            {"$match": {"event_type": "solution_view", "created_at": {"$gte": since}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ])
        category_docs = [d async for d in category_cursor]
        total_views = sum(d["count"] for d in category_docs) or 1
        trending_categories = [
            {
                "name": d["_id"] or "Unknown",
                "count": d["count"],
                "pct": round(d["count"] / total_views * 100, 1),
            }
            for d in category_docs if d["_id"]
        ]

        # Popular search queries
        search_cursor = db.analytics_events.find(
            {"event_type": "search_query", "created_at": {"$gte": since}},
            {"query": 1},
        ).sort("created_at", -1).limit(200)
        search_docs = [d async for d in search_cursor]
        query_counts: Counter = Counter(
            d["query"].lower().strip()
            for d in search_docs
            if d.get("query")
        )
        popular_searches: List[str] = [q for q, _ in query_counts.most_common(10)]

        # Top solutions by view count
        top_cursor = db.analytics_events.aggregate([
            {"$match": {"event_type": "solution_view", "created_at": {"$gte": since}}},
            {"$group": {"_id": "$solution_id", "view_count": {"$sum": 1}}},
            {"$sort": {"view_count": -1}},
            {"$limit": 5},
        ])
        top_solution_docs = [d async for d in top_cursor]
        top_solutions = [
            {"solution_id": str(d["_id"]), "view_count": d["view_count"]}
            for d in top_solution_docs if d["_id"]
        ]

        # Match success rate (matches that led to purchases)
        total_matches = await db.match_runs.count_documents(
            {"status": "completed", "created_at": {"$gte": since}}
        )
        total_purchases = await db.transactions.count_documents(
            {"status": {"$in": ["completed", "escrowed"]}, "created_at": {"$gte": since}}
        )
        match_conversion_rate = round(
            (total_purchases / total_matches * 100) if total_matches > 0 else 0, 1
        )

        result = {
            "trending_categories": trending_categories,
            "popular_searches": popular_searches,
            "top_solutions": top_solutions,
            "match_conversion_rate_pct": match_conversion_rate,
            "total_matches_30d": total_matches,
            "total_purchases_30d": total_purchases,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "window_days": 30,
        }

        # Store in cache collection (upsert)
        await db.market_intelligence_cache.replace_one(
            {"_id": "latest"},
            {"_id": "latest", **result},
            upsert=True,
        )

        return result


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await MarketIntelligenceAgent().execute(ctx, run_id=ctx.get("run_id"))
