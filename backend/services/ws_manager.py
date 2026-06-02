"""Per-run WebSocket broadcast manager.

Concurrency model:
  - Each orchestration run gets its own channel keyed by `run_id`.
  - Subscribers connect via WS /api/ws/match/{run_id} and are added to that
    channel's connection set ONLY.
  - Broadcasts are scoped to a single run_id; events from run A NEVER reach
    subscribers of run B. There is no global broadcast surface.
  - Events emitted before any subscriber connects are buffered per-run so that
    a late subscriber can replay the full event sequence (important for short
    pipelines).
  - All mutations to the per-run state happen under an asyncio.Lock that is
    itself per-run (no global lock, so different runs never contend).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from fastapi import WebSocket

from services.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class _RunChannel:
    connections: Set[WebSocket] = field(default_factory=set)
    buffer: List[Dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class WSManager:
    def __init__(self) -> None:
        self._channels: Dict[str, _RunChannel] = {}
        self._channels_lock = asyncio.Lock()

    async def _get_channel(self, run_id: str) -> _RunChannel:
        async with self._channels_lock:
            ch = self._channels.get(run_id)
            if ch is None:
                ch = _RunChannel()
                self._channels[run_id] = ch
            return ch

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        ch = await self._get_channel(run_id)
        # Hold the channel lock for the WHOLE flow:
        #   1) snapshot the buffer
        #   2) flush replay to the new subscriber
        #   3) add this socket to the live connection set
        # This guarantees per-stream monotonic ordering: any concurrent
        # broadcast will queue behind this lock and only reach the new
        # subscriber AFTER the replay is fully delivered.
        async with ch.lock:
            replay = list(ch.buffer)
            finished = ch.finished
            for evt in replay:
                try:
                    await websocket.send_text(json.dumps(evt))
                except Exception:
                    # Connection dropped during replay — abort and exit.
                    return
            ch.connections.add(websocket)
        if finished:
            # Inform late subscriber that run is done; they may close on their side.
            try:
                await websocket.send_text(json.dumps({"type": "run_already_finished", "run_id": run_id}))
            except Exception:
                pass

    async def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        ch = self._channels.get(run_id)
        if ch is None:
            return
        async with ch.lock:
            ch.connections.discard(websocket)

    async def broadcast(self, run_id: str, event: Dict[str, Any]) -> None:
        ch = await self._get_channel(run_id)
        payload = json.dumps(event)
        dead: List[WebSocket] = []
        async with ch.lock:
            ch.buffer.append(event)
            connections = list(ch.connections)
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with ch.lock:
                for ws in dead:
                    ch.connections.discard(ws)

    async def mark_finished(self, run_id: str) -> None:
        ch = await self._get_channel(run_id)
        async with ch.lock:
            ch.finished = True

    async def cleanup(self, run_id: str) -> None:
        """Free the per-run channel memory once no subscribers remain."""
        async with self._channels_lock:
            ch = self._channels.get(run_id)
            if ch and ch.finished and not ch.connections:
                self._channels.pop(run_id, None)

    def channel_counts(self) -> Dict[str, Any]:
        """Introspection snapshot for tests / debugging."""
        per_run = {
            rid: {
                "connections": len(ch.connections),
                "buffered_events": len(ch.buffer),
                "finished": ch.finished,
            }
            for rid, ch in self._channels.items()
        }
        return {
            "total_channels": len(self._channels),
            "total_connections": sum(v["connections"] for v in per_run.values()),
            "per_run": per_run,
        }


_singleton: WSManager | None = None


def get_ws_manager() -> WSManager:
    global _singleton
    if _singleton is None:
        _singleton = WSManager()
    return _singleton
