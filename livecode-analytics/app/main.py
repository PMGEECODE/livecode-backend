import contextlib
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.ingest import AnalyticsIngestQueue
from app.schemas import (
    AnalyticsBatchCreate,
    AnalyticsEventCreate,
    AnalyticsIngestResponse,
    AnalyticsSummaryResponse,
    HealthResponse,
)
from app.security import client_ip, hash_ip, require_admin_token
from app.storage import AnalyticsStore, to_stored_event

settings = get_settings()
store = AnalyticsStore(settings.ANALYTICS_DATABASE_URL)
ingest_queue = AnalyticsIngestQueue(
    store=store,
    max_size=settings.ANALYTICS_QUEUE_MAX_SIZE,
    flush_batch_size=settings.ANALYTICS_FLUSH_BATCH_SIZE,
    flush_interval_seconds=settings.ANALYTICS_FLUSH_INTERVAL_SECONDS,
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_db()
    await ingest_queue.start()
    yield
    await ingest_queue.stop()
    await store.close()



app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )


def _stored_events_from_payload(request: Request, events: list[AnalyticsEventCreate]):
    ip_hash = hash_ip(client_ip(request), settings)
    user_agent = request.headers.get("user-agent")
    return [
        to_stored_event(event, user_agent=user_agent, ip_hash=ip_hash)
        for event in events
    ]


@app.post("/analytics/track", response_model=AnalyticsIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def track_event(request: Request, payload: AnalyticsEventCreate) -> AnalyticsIngestResponse:
    accepted, dropped = await ingest_queue.enqueue_many(_stored_events_from_payload(request, [payload]))
    return AnalyticsIngestResponse(accepted=accepted, dropped=dropped, queued=ingest_queue.queued_count)


@app.post("/analytics/batch", response_model=AnalyticsIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def track_batch(request: Request, payload: AnalyticsBatchCreate) -> AnalyticsIngestResponse:
    if len(payload.events) > settings.ANALYTICS_BATCH_MAX_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Analytics batches are limited to {settings.ANALYTICS_BATCH_MAX_EVENTS} events.",
        )
    accepted, dropped = await ingest_queue.enqueue_many(_stored_events_from_payload(request, payload.events))
    return AnalyticsIngestResponse(accepted=accepted, dropped=dropped, queued=ingest_queue.queued_count)


@app.post("/analytics/flush", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin_token)])
async def flush_events() -> Response:
    await ingest_queue.flush_all()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
async def get_summary(days: int = 30) -> dict:
    await ingest_queue.flush_all()
    days = max(1, min(days, 365))
    return await store.summary(days)


@app.get("/analytics/stream")
async def analytics_stream(request: Request, _admin=Depends(require_admin_token)):
    import asyncio
    from fastapi.responses import StreamingResponse
    from app.broadcaster import broadcaster

    async def event_generator():
        q = broadcaster.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    oldest = await store.oldest_event_at()
    oldest_dt = datetime.fromisoformat(oldest) if oldest else None
    return HealthResponse(
        status="ok",
        queued=ingest_queue.queued_count,
        stored_events=await store.count(),
        oldest_event_at=oldest_dt,
    )
