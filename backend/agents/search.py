"""SemanticSearchAgent — hybrid vector + keyword retrieval over the catalogue."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Set

from db import get_db
from services.vector_index import get_vector_index


DEFAULT_TOP_K = 12
EXPANDED_TOP_K = 20
KEYWORD_FALLBACK_THRESHOLD = 3


async def run(ctx: Dict[str, Any]) -> Dict[str, Any]:
    vector_index = get_vector_index()
    db = get_db()

    query_vec: List[float] = ctx.get("query_vector") or []
    parsed = ctx.get("parsed_requirement", {}) or {}

    # Build keyword query (Mongo text search) from parsed features + category.
    keyword_terms: List[str] = []
    if parsed.get("category"):
        keyword_terms.append(str(parsed["category"]))
    keyword_terms.extend(str(f) for f in parsed.get("required_features", []) or [])
    keyword_terms.extend(str(t) for t in parsed.get("tags", []) or [])
    keyword_query = " ".join(keyword_terms) or ctx.get("normalized_text", "")

    t0 = time.perf_counter()
    keyword_results: List[Dict[str, Any]] = []
    if keyword_query.strip():
        try:
            cursor = db.solutions.find(
                {"$text": {"$search": keyword_query}},
                {"score": {"$meta": "textScore"}, "_id": 1, "title": 1, "category": 1},
            ).sort([("score", {"$meta": "textScore"})]).limit(15)
            keyword_results = [d async for d in cursor]
        except Exception:
            # If text index missing for any reason, gracefully fall back.
            keyword_results = []
    keyword_ms = int((time.perf_counter() - t0) * 1000)

    # Vector results
    top_k = DEFAULT_TOP_K
    if len(keyword_results) < KEYWORD_FALLBACK_THRESHOLD:
        top_k = EXPANDED_TOP_K

    t1 = time.perf_counter()
    vector_hits = await vector_index.query(query_vec, top_k=top_k) if query_vec else []
    vector_ms = int((time.perf_counter() - t1) * 1000)

    # Merge + dedupe (vector first, keyword fills the rest).
    seen: Set[str] = set()
    merged: List[Dict[str, Any]] = []
    method_tags: Dict[str, List[str]] = {}
    for sid, sim in vector_hits:
        if sid not in seen:
            seen.add(sid)
            merged.append({"solution_id": sid, "vector_score": sim})
            method_tags.setdefault(sid, []).append("vector")
    for d in keyword_results:
        sid = d["_id"]
        if sid not in seen:
            seen.add(sid)
            merged.append({"solution_id": sid, "text_score": float(d.get("score", 0))})
            method_tags.setdefault(sid, []).append("keyword")
        else:
            method_tags[sid].append("keyword")

    candidate_ids = [m["solution_id"] for m in merged]
    retrieval_latency_ms = keyword_ms + vector_ms
    return {
        "candidate_ids": candidate_ids,
        "candidates_meta": merged,
        "retrieval_methods": method_tags,
        "retrieval_latency_ms": retrieval_latency_ms,
        "keyword_query": keyword_query,
        "keyword_count": len(keyword_results),
        "vector_count": len(vector_hits),
        "top_k_used": top_k,
    }
