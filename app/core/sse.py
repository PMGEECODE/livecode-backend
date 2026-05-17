import asyncio
import json
from typing import Set
import logging

logger = logging.getLogger(__name__)

class SSEManager:
    """
    Manages active Server-Sent Events (SSE) connections.
    Uses asyncio.Queue for safe event consumption and provides a thread/coroutine-safe 
    broadcast mechanism to all active browser client listeners.
    """
    def __init__(self):
        self._listeners: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribes a new connection queue to the manager.
        """
        queue = asyncio.Queue()
        async with self._lock:
            self._listeners.add(queue)
            logger.info(f"🔌 New SSE subscriber connected. Total active streams: {len(self._listeners)}")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Unsubscribes a connection queue, freeing up system memory.
        """
        async with self._lock:
            if queue in self._listeners:
                self._listeners.remove(queue)
                logger.info(f"🔌 SSE subscriber disconnected. Total active streams: {len(self._listeners)}")

    async def broadcast(self, event_type: str, data: dict) -> None:
        """
        Broadcasts a message payload to all actively connected clients.
        """
        payload = {
            "event": event_type,
            "data": data
        }
        serialized = json.dumps(payload)
        
        async with self._lock:
            if not self._listeners:
                return
            
            logger.info(f"📢 Broadcasting real-time SSE event '{event_type}' to {len(self._listeners)} listeners.")
            for queue in self._listeners:
                await queue.put(serialized)

# Global instance of the real-time event broadcaster
sse_manager = SSEManager()
