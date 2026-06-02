import asyncio
from collections import deque
from typing import Iterable

from app.storage import AnalyticsStore, StoredEvent


class AnalyticsIngestQueue:
    def __init__(
        self,
        *,
        store: AnalyticsStore,
        max_size: int,
        flush_batch_size: int,
        flush_interval_seconds: float,
    ) -> None:
        self.store = store
        self.max_size = max(1, max_size)
        self.flush_batch_size = max(1, flush_batch_size)
        self.flush_interval_seconds = max(0.2, flush_interval_seconds)
        self._queue: deque[StoredEvent] = deque()
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None

    @property
    def queued_count(self) -> int:
        return len(self._queue)

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._worker_task:
            await self._worker_task
        await self.flush_all()

    async def enqueue_many(self, events: Iterable[StoredEvent]) -> tuple[int, int]:
        accepted = 0
        dropped = 0
        async with self._lock:
            for event in events:
                if len(self._queue) >= self.max_size:
                    dropped += 1
                    continue
                self._queue.append(event)
                accepted += 1
        return accepted, dropped

    async def flush_once(self) -> int:
        batch: list[StoredEvent] = []
        async with self._lock:
            while self._queue and len(batch) < self.flush_batch_size:
                batch.append(self._queue.popleft())
        if not batch:
            return 0
        inserted = await self.store.insert_events(batch)
        if inserted:
            from app.broadcaster import broadcaster
            broadcaster.broadcast("update")
        return inserted

    async def flush_all(self) -> int:
        total = 0
        while self.queued_count:
            total += await self.flush_once()
        return total

    async def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.flush_interval_seconds)
            except asyncio.TimeoutError:
                await self.flush_once()
