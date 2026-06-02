"""V1 multi-channel WebSocket manager — keyed by (namespace, channel_id).
Used by messaging (`conversations:{user_id}`) and deployments (`deployments:{id}`).
Independent of Phase-0 `services.ws_manager` (which is run-id scoped).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from fastapi import WebSocket


@dataclass
class _Channel:
    connections: Set[WebSocket] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class V1WSManager:
    def __init__(self) -> None:
        self._channels: Dict[Tuple[str, str], _Channel] = {}
        self._lock = asyncio.Lock()

    async def _get(self, namespace: str, channel_id: str) -> _Channel:
        key = (namespace, channel_id)
        async with self._lock:
            ch = self._channels.get(key)
            if ch is None:
                ch = _Channel()
                self._channels[key] = ch
            return ch

    async def connect(self, namespace: str, channel_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        ch = await self._get(namespace, channel_id)
        async with ch.lock:
            ch.connections.add(websocket)

    async def disconnect(self, namespace: str, channel_id: str, websocket: WebSocket) -> None:
        ch = self._channels.get((namespace, channel_id))
        if not ch:
            return
        async with ch.lock:
            ch.connections.discard(websocket)
        async with self._lock:
            if not ch.connections:
                self._channels.pop((namespace, channel_id), None)

    async def broadcast(self, namespace: str, channel_id: str, event: Dict[str, Any]) -> None:
        ch = await self._get(namespace, channel_id)
        payload = json.dumps(event, default=str)
        async with ch.lock:
            connections = list(ch.connections)
        dead: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with ch.lock:
                for ws in dead:
                    ch.connections.discard(ws)


_singleton: V1WSManager | None = None


def get_v1_ws() -> V1WSManager:
    global _singleton
    if _singleton is None:
        _singleton = V1WSManager()
    return _singleton
