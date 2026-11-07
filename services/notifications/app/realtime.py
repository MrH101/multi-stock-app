"""WebSocket fan-out to connected users, keyed by organisation.

Connections live in this process. To run several replicas, publish pushes to a
Redis pub/sub channel and have every replica forward to its local sockets.
"""
import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("realtime")


class ConnectionManager:
    def __init__(self):
        self._by_org: dict[int, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, org_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._by_org[org_id].add(ws)

    def disconnect(self, org_id: int, ws: WebSocket) -> None:
        self._by_org[org_id].discard(ws)

    async def push(self, org_id: int, message: dict) -> None:
        for ws in list(self._by_org.get(org_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(org_id, ws)

    def push_threadsafe(self, org_id: int, message: dict) -> None:
        """Push from sync (threadpool) code such as request handlers."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.push(org_id, message), self.loop)


manager = ConnectionManager()
