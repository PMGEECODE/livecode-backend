import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt


def load_app(monkeypatch, tmp_path, *, queue_max_size=100):
    monkeypatch.setenv("ANALYTICS_DATABASE_PATH", str(tmp_path / "analytics.sqlite3"))
    monkeypatch.setenv("ANALYTICS_QUEUE_MAX_SIZE", str(queue_max_size))
    monkeypatch.setenv("ANALYTICS_FLUSH_BATCH_SIZE", "20")
    monkeypatch.setenv("ANALYTICS_FLUSH_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("ANALYTICS_BATCH_MAX_EVENTS", "50")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ANALYTICS_ADMIN_SUBJECTS", "admin-user")

    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]

    module = importlib.import_module("app.main")
    return module.app, module.ingest_queue


def admin_token(subject="admin-user"):
    return jwt.encode(
        {"sub": subject, "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        "test-secret",
        algorithm="HS256",
    )


def sample_event(**overrides):
    event = {
        "event_name": "page_engagement",
        "page_path": "/trainings?secret=not-from-clicks",
        "page_title": "Trainings",
        "session_id": "session-1",
        "duration_ms": 12_000,
        "scroll_depth_percent": 70,
        "interaction_count": 3,
        "metadata": {"label": "Register", "nested": {"ignored": True}},
    }
    event.update(overrides)
    return event


def test_batch_ingest_queues_and_summary_flushes(monkeypatch, tmp_path):
    app, ingest_queue = load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post("/analytics/batch", json={"events": [sample_event()]})
        assert response.status_code == 202
        assert response.json()["accepted"] == 1
        assert ingest_queue.queued_count == 1

        summary = client.get(
            "/analytics/summary?days=30",
            headers={"Authorization": f"Bearer {admin_token()}"},
        )
        assert summary.status_code == 200
        data = summary.json()
        assert data["total_events"] == 1
        assert data["avg_duration_seconds"] == 12
        assert data["avg_scroll_depth_percent"] == 70
        assert data["total_interactions"] == 3
        assert data["top_pages"][0]["page_path"] == "/trainings?secret=not-from-clicks"


def test_summary_rejects_missing_or_unapproved_admin_token(monkeypatch, tmp_path):
    app, _ = load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        assert client.get("/analytics/summary").status_code == 401
        response = client.get(
            "/analytics/summary",
            headers={"Authorization": f"Bearer {admin_token('other-user')}"},
        )
        assert response.status_code == 403


def test_queue_is_bounded_and_drops_excess_events(monkeypatch, tmp_path):
    app, ingest_queue = load_app(monkeypatch, tmp_path, queue_max_size=2)

    with TestClient(app) as client:
        response = client.post(
            "/analytics/batch",
            json={"events": [sample_event(session_id=f"s-{idx}") for idx in range(5)]},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 2
        assert data["dropped"] == 3
        assert ingest_queue.queued_count == 2


def test_rejects_oversized_batch_and_unsupported_event(monkeypatch, tmp_path):
    app, _ = load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        too_many = [sample_event(session_id=f"s-{idx}") for idx in range(51)]
        response = client.post("/analytics/batch", json={"events": too_many})
        assert response.status_code == 413

        invalid = client.post("/analytics/track", json=sample_event(event_name="password_captured"))
        assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (-100, 0),
        (101, 100),
        (42, 42),
    ],
)
def test_scroll_depth_is_clamped(monkeypatch, tmp_path, raw, expected):
    app, _ = load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post("/analytics/track", json=sample_event(scroll_depth_percent=raw))
        assert response.status_code == 202
        summary = client.get(
            "/analytics/summary",
            headers={"Authorization": f"Bearer {admin_token()}"},
        )
        assert summary.json()["avg_scroll_depth_percent"] == expected
