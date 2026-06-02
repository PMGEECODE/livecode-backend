import asyncio

class EventBroadcaster:
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def broadcast(self, message: str) -> None:
        for q in self.subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

broadcaster = EventBroadcaster()
