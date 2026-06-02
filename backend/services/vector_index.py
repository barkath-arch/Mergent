"""In-process vector similarity index.

Local MongoDB does NOT support Atlas $vectorSearch. As documented in
MIGRATION_NOTES.md, Phase 0 ships a real cosine-similarity ANN-free index
backed by numpy. It is rebuilt from `solutions` documents on demand
(typically after embedding tasks finish).
"""
from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

import numpy as np

from services.logging_config import get_logger

logger = get_logger(__name__)


class VectorIndex:
    """Thread-safe (asyncio-locked) cosine-similarity index over solution embeddings."""

    def __init__(self) -> None:
        self._ids: List[str] = []
        self._matrix: Optional[np.ndarray] = None  # shape (N, D), L2-normalized
        self._dim: Optional[int] = None
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._ids)

    @property
    def dim(self) -> Optional[int]:
        return self._dim

    async def rebuild(self, items: List[Tuple[str, List[float]]]) -> None:
        """Replace the in-memory index with a fresh set of (id, vector) tuples."""
        async with self._lock:
            if not items:
                self._ids = []
                self._matrix = None
                self._dim = None
                logger.info("vector_index_rebuilt", extra={"size": 0})
                return

            ids = [sid for sid, _ in items]
            vecs = np.array([v for _, v in items], dtype=np.float32)
            # L2-normalize so cosine = dot product.
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            vecs = vecs / norms

            self._ids = ids
            self._matrix = vecs
            self._dim = int(vecs.shape[1])
            logger.info("vector_index_rebuilt", extra={"size": len(ids), "dim": self._dim})

    async def upsert(self, solution_id: str, vector: List[float]) -> None:
        async with self._lock:
            v = np.array(vector, dtype=np.float32)
            n = np.linalg.norm(v)
            v = v / (n if n > 0 else 1e-12)
            if solution_id in self._ids:
                idx = self._ids.index(solution_id)
                assert self._matrix is not None
                self._matrix[idx] = v
            else:
                if self._matrix is None:
                    self._matrix = v.reshape(1, -1)
                    self._dim = v.shape[0]
                else:
                    self._matrix = np.vstack([self._matrix, v.reshape(1, -1)])
                self._ids.append(solution_id)

    async def query(self, vector: List[float], top_k: int = 12) -> List[Tuple[str, float]]:
        """Return [(solution_id, cosine_sim)] sorted by sim desc."""
        async with self._lock:
            if self._matrix is None or not self._ids:
                return []
            q = np.array(vector, dtype=np.float32)
            n = np.linalg.norm(q)
            q = q / (n if n > 0 else 1e-12)
            sims = self._matrix @ q
            k = min(top_k, len(self._ids))
            top_idx = np.argpartition(-sims, k - 1)[:k]
            # Stable sort within top-k by similarity desc.
            top_idx = top_idx[np.argsort(-sims[top_idx])]
            return [(self._ids[int(i)], float(sims[int(i)])) for i in top_idx]


# Singleton
_singleton: Optional[VectorIndex] = None


def get_vector_index() -> VectorIndex:
    global _singleton
    if _singleton is None:
        _singleton = VectorIndex()
    return _singleton
