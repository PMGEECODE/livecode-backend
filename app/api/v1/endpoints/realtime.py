import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.sse import sse_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/stream")
async def sse_stream():
    """
    Exposes a real-time Server-Sent Events stream for connected applications.
    Emits keep-alive comments (heartbeats) every 15 seconds to prevent proxies 
    from terminating idle connections.
    """
    queue = await sse_manager.subscribe()
    
    async def event_generator():
        try:
            while True:
                try:
                    # Wait for next broadcast message or trigger ping heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send a lightweight ping to keep connection open
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            # Browser session cancelled / terminated stream connection
            logger.info("🔌 Client closed SSE stream channel.")
        finally:
            await sse_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disables buffering on proxy systems (e.g. Nginx, Cloudflare)
        }
    )
