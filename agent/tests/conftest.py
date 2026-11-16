"""Shared pytest fixtures for agent tests."""

from __future__ import annotations

import pytest


@pytest.fixture()
def redis_client(monkeypatch):
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    from app import redis_client as rc

    rc.get_redis.cache_clear()
    monkeypatch.setattr(rc, "get_redis", lambda: client)
    monkeypatch.setattr(rc, "redis_enabled", lambda: True)
    return client
