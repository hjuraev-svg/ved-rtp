"""In-process pub/sub that pushes change events to every open dashboard.

Single API container -> a plain in-memory set is enough. If you ever scale the
api service beyond one replica, swap `broadcast` for a Redis pub/sub fan-out;
the call sites do not change.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

log = logging.getLogger("ved.realtime")


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("ws connected (%d total)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: str, payload: dict | None = None) -> None:
        message = json.dumps(
            {
                "event": event,
                "payload": payload or {},
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = Hub()
