import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Iterable

from fastapi import WebSocket

logger = logging.getLogger("crop_backend.social.realtime")


class SocialConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        sockets = self._connections.get(user_id)
        return bool(sockets)

    async def send_to_user(self, user_id: str, payload: Dict[str, Any]) -> None:
        sockets = list(self._connections.get(user_id, set()))
        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(user_id, websocket)

    async def send_to_many(self, user_ids: Iterable[str], payload: Dict[str, Any]) -> None:
        for user_id in user_ids:
            await self.send_to_user(user_id, payload)


social_connection_manager = SocialConnectionManager()