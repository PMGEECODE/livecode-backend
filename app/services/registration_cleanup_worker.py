import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.config import settings
from app.db.models.registration import CourseRegistration
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

async def cleanup_pending_registrations() -> None:
    # Delete pending or failed registrations older than 1 hour
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
    
    try:
        async with SessionLocal() as db:
            stmt = delete(CourseRegistration).where(
                CourseRegistration.status.in_(["pending", "failed"]),
                CourseRegistration.created_at <= cutoff_time
            )
            result = await db.execute(stmt)
            await db.commit()
            
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"🧹 Cleaned up {deleted_count} abandoned (pending/failed) course registrations older than 1 hour.")
    except Exception as e:
        logger.error(f"❌ Failed to clean up abandoned registrations: {e}")

async def registration_cleanup_worker(stop_event: asyncio.Event) -> None:
    logger.info("Registration cleanup worker started. Will run every 30 minutes.")
    
    # Run loop every 30 minutes (1800 seconds)
    interval_seconds = 1800
    
    while not stop_event.is_set():
        try:
            await cleanup_pending_registrations()
        except Exception as exc:
            logger.error("Registration cleanup worker cycle failed: %s", exc)
            
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
            
    logger.info("Registration cleanup worker stopped.")
