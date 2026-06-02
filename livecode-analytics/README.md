# Livecode Analytics Service

Standalone analytics ingestion service for Livecode Technologies.

The client sends analytics directly here instead of through the main backend. Requests are accepted into a bounded in-memory queue, then a background worker bulk-writes events to the analytics database. If traffic spikes beyond the queue limit, extra analytics events are dropped instead of slowing payments, registrations, or the main API.

## Run Locally

```bash
cd livecode-analytics
python -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Client/admin env:

```bash
VITE_ANALYTICS_API_BASE_URL=http://localhost:8010
```

Production should use the deployed analytics service URL, for example:

```bash
VITE_ANALYTICS_API_BASE_URL=https://analytics.livecodetechnologies.com
```

## Endpoints

- `POST /analytics/batch`: public analytics ingestion.
- `POST /analytics/track`: public single-event compatibility endpoint.
- `GET /analytics/summary`: admin summary, requires a valid bearer JWT signed with `SECRET_KEY`.
- `POST /analytics/flush`: admin-only manual flush.
- `GET /health`: service health and queue depth.

## Scaling Notes

- Increase `ANALYTICS_QUEUE_MAX_SIZE` for larger traffic bursts.
- Increase `ANALYTICS_FLUSH_BATCH_SIZE` to reduce write frequency.
- Use a persistent database volume for `var/analytics.sqlite3`, or replace the storage adapter with Postgres/ClickHouse later without changing the frontend contract.
