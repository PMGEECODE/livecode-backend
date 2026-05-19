import pytest
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.redis import redis_manager

client = TestClient(app)

@pytest.mark.asyncio
async def test_redis_manager_get_fallback():
    """Verify that redis_manager gets fall back gracefully when client is not initialized."""
    redis_manager.client = None
    val = await redis_manager.get("some_key")
    assert val is None

@pytest.mark.asyncio
async def test_redis_manager_set_fallback():
    """Verify that redis_manager sets fall back gracefully when client is not initialized."""
    redis_manager.client = None
    success = await redis_manager.set("some_key", "some_value")
    assert success is False

@pytest.mark.asyncio
async def test_redis_manager_delete_fallback():
    """Verify that redis_manager deletes fall back gracefully when client is not initialized."""
    redis_manager.client = None
    success = await redis_manager.delete("some_key")
    assert success is False

@pytest.mark.asyncio
async def test_redis_manager_delete_pattern_fallback():
    """Verify that redis_manager pattern deletes fall back gracefully when client is not initialized."""
    redis_manager.client = None
    success = await redis_manager.delete_pattern("courses:*")
    assert success is False


