import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import asyncpg

from app.schemas import ALLOWED_ANALYTICS_EVENTS, AnalyticsEventCreate

logger = logging.getLogger(__name__)


@dataclass
class StoredEvent:
    event_name: str
    page_path: str | None
    page_title: str | None
    entity_type: str | None
    entity_id: str | None
    entity_title: str | None
    referrer: str | None
    session_id: str | None
    duration_ms: int | None
    scroll_depth_percent: int | None
    interaction_count: int | None
    metadata_json: dict[str, Any] | None
    user_agent: str | None
    ip_hash: str | None
    created_at: str


class AnalyticsStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None
        self._write_lock = asyncio.Lock()

    async def init_db(self) -> None:
        self._pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id SERIAL PRIMARY KEY,
                    event_name TEXT NOT NULL,
                    page_path TEXT,
                    page_title TEXT,
                    entity_type TEXT,
                    entity_id TEXT,
                    entity_title TEXT,
                    referrer TEXT,
                    session_id TEXT,
                    duration_ms INTEGER,
                    scroll_depth_percent INTEGER,
                    interaction_count INTEGER,
                    metadata_json TEXT,
                    user_agent TEXT,
                    ip_hash TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
            for column in (
                "event_name",
                "page_path",
                "entity_type",
                "entity_id",
                "session_id",
                "created_at",
            ):
                await conn.execute(
                    f"CREATE INDEX IF NOT EXISTS ix_analytics_events_{column} ON analytics_events ({column})"
                )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def insert_events(self, events: Iterable[StoredEvent]) -> int:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        rows = [
            (
                event.event_name,
                event.page_path,
                event.page_title,
                event.entity_type,
                event.entity_id,
                event.entity_title,
                event.referrer,
                event.session_id,
                event.duration_ms,
                event.scroll_depth_percent,
                event.interaction_count,
                json.dumps(event.metadata_json, separators=(",", ":")) if event.metadata_json else None,
                event.user_agent,
                event.ip_hash,
                datetime.fromisoformat(event.created_at).replace(tzinfo=timezone.utc),
            )
            for event in events
        ]
        if not rows:
            return 0

        async with self._write_lock:
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO analytics_events (
                        event_name, page_path, page_title, entity_type, entity_id, entity_title,
                        referrer, session_id, duration_ms, scroll_depth_percent, interaction_count,
                        metadata_json, user_agent, ip_hash, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    """,
                    rows,
                )
        return len(rows)

    async def summary(self, days: int) -> dict[str, Any]:
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        since = datetime.now(timezone.utc) - timedelta(days=days)

        async with self._pool.acquire() as conn:
            total_events = await conn.fetchval(
                "SELECT COUNT(*) FROM analytics_events WHERE created_at >= $1", since
            )
            total_sessions = await conn.fetchval(
                "SELECT COUNT(DISTINCT session_id) FROM analytics_events WHERE created_at >= $1 AND session_id IS NOT NULL",
                since,
            )
            avg_duration_ms = await conn.fetchval(
                "SELECT AVG(duration_ms) FROM analytics_events WHERE created_at >= $1 AND duration_ms IS NOT NULL",
                since,
            )
            avg_scroll = await conn.fetchval(
                "SELECT AVG(scroll_depth_percent) FROM analytics_events WHERE created_at >= $1 AND scroll_depth_percent IS NOT NULL",
                since,
            )
            total_interactions = await conn.fetchval(
                "SELECT SUM(interaction_count) FROM analytics_events WHERE created_at >= $1 AND interaction_count IS NOT NULL",
                since,
            )

            event_counts_rows = await conn.fetch(
                "SELECT event_name, COUNT(*) AS count FROM analytics_events WHERE created_at >= $1 GROUP BY event_name",
                since,
            )
            event_counts = {row["event_name"]: row["count"] for row in event_counts_rows}

            top_entities_rows = await conn.fetch(
                """
                SELECT entity_type, entity_id, entity_title, COUNT(*) AS count
                FROM analytics_events
                WHERE created_at >= $1 AND entity_id IS NOT NULL
                GROUP BY entity_type, entity_id, entity_title
                ORDER BY count DESC
                LIMIT 10
                """,
                since,
            )
            top_entities = [dict(row) for row in top_entities_rows]

            top_pages_rows = await conn.fetch(
                """
                SELECT
                    page_path,
                    COUNT(*) AS views,
                    COUNT(DISTINCT session_id) AS sessions,
                    AVG(duration_ms) AS avg_duration_ms,
                    AVG(scroll_depth_percent) AS avg_scroll,
                    SUM(interaction_count) AS interactions
                FROM analytics_events
                WHERE created_at >= $1
                  AND page_path IS NOT NULL
                  AND event_name IN ('page_view', 'page_engagement')
                GROUP BY page_path
                ORDER BY views DESC
                LIMIT 10
                """,
                since,
            )
            top_pages = [
                {
                    "page_path": row["page_path"],
                    "views": row["views"],
                    "sessions": row["sessions"],
                    "avg_duration_seconds": round((float(row["avg_duration_ms"]) if row["avg_duration_ms"] else 0) / 1000, 1),
                    "avg_scroll_depth_percent": round(float(row["avg_scroll"]) if row["avg_scroll"] else 0, 1),
                    "interactions": int(row["interactions"]) if row["interactions"] else 0,
                }
                for row in top_pages_rows
            ]

            recent_events_rows = await conn.fetch(
                """
                SELECT id, event_name, page_path, entity_type, entity_id, entity_title,
                       duration_ms, scroll_depth_percent, interaction_count, created_at
                FROM analytics_events
                WHERE created_at >= $1
                ORDER BY created_at DESC
                LIMIT 25
                """,
                since,
            )
            recent_events = [
                {
                    **dict(row),
                    "created_at": row["created_at"].isoformat()
                }
                for row in recent_events_rows
            ]

        return {
            "days": days,
            "total_events": total_events or 0,
            "total_sessions": total_sessions or 0,
            "avg_duration_seconds": round((float(avg_duration_ms) if avg_duration_ms else 0) / 1000, 1),
            "avg_scroll_depth_percent": round(float(avg_scroll) if avg_scroll else 0, 1),
            "total_interactions": int(total_interactions) if total_interactions else 0,
            "events": [
                {"event_name": event_name, "count": event_counts.get(event_name, 0)}
                for event_name in sorted(ALLOWED_ANALYTICS_EVENTS)
            ],
            "top_entities": top_entities,
            "top_pages": top_pages,
            "recent_events": recent_events,
        }

    async def count(self) -> int:
        if not self._pool:
            return 0
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM analytics_events") or 0

    async def oldest_event_at(self) -> str | None:
        if not self._pool:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT MIN(created_at) FROM analytics_events")
            if row and row[0]:
                return row[0].isoformat()
            return None


def to_stored_event(
    event: AnalyticsEventCreate,
    *,
    user_agent: str | None,
    ip_hash: str | None,
) -> StoredEvent:
    return StoredEvent(
        event_name=event.event_name,
        page_path=event.page_path,
        page_title=event.page_title,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        entity_title=event.entity_title,
        referrer=event.referrer,
        session_id=event.session_id,
        duration_ms=event.duration_ms,
        scroll_depth_percent=event.scroll_depth_percent,
        interaction_count=event.interaction_count,
        metadata_json=event.metadata,
        user_agent=(user_agent or "")[:800] or None,
        ip_hash=ip_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
