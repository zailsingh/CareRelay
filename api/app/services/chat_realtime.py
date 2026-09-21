import asyncio
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class ChatConnectionManager:
    """Single-process fan-out. Replace behind this boundary for multi-instance deployment."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, care_profile_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[care_profile_id].add(websocket)

    async def disconnect(self, care_profile_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(care_profile_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(care_profile_id, None)

    async def broadcast(self, care_profile_id: UUID, payload: dict) -> None:
        async with self._lock:
            connections = list(self._connections.get(care_profile_id, set()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except (OSError, RuntimeError):
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(care_profile_id, websocket)


chat_connections = ChatConnectionManager()
