import asyncio
import json
import logging
import redis
from app.core.redis import redis_manager
from app.core.email import send_email_async

logger = logging.getLogger(__name__)

async def support_email_worker(stop_event: asyncio.Event) -> None:
    """
    Background worker that monitors a Redis queue for offline support request emails.
    Pop payloads and sends them asynchronously using send_email_async.
    """
    logger.info("📬 Support email worker initialized.")
    while not stop_event.is_set():
        if not redis_manager.client:
            await asyncio.sleep(2)
            continue
        try:
            # blpop blocks up to 1 second waiting for an item in the list
            res = await redis_manager.client.blpop("support:email_queue", timeout=1)
            if res:
                _, payload_raw = res
                payload = json.loads(payload_raw)
                to_email = payload.get("to_email")
                subject = payload.get("subject")
                html_body = payload.get("html_body")
                
                if to_email and subject and html_body:
                    logger.info(f"📧 Support worker sending email notification to {to_email}")
                    await send_email_async(to_email, subject, html_body)
        except asyncio.CancelledError:
            break
        except (redis.exceptions.TimeoutError, asyncio.TimeoutError, TimeoutError):
            # Normal timeout when the queue is empty; continue the loop
            continue
        except Exception as exc:
            logger.error("❌ Support email worker cycle error: %s", exc)
            await asyncio.sleep(2)
            
    logger.info("📬 Support email worker stopped.")
