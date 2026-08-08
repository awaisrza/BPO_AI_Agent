"""Shared Redis connection for call routing (optional — degrades when unset)."""

from __future__ import annotations

import os
from functools import lru_cache

from loguru import logger

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]


def redis_enabled() -> bool:
    return bool((os.getenv("REDIS_URL") or os.getenv("REDIS_HOST") or "").strip())


def redis_url() -> str:
    explicit = (os.getenv("REDIS_URL") or "").strip()
    if explicit:
        return explicit
    host = (os.getenv("REDIS_HOST") or "127.0.0.1").strip()
    port = (os.getenv("REDIS_PORT") or "6379").strip()
    db = (os.getenv("REDIS_DB") or "0").strip()
    password = (os.getenv("REDIS_PASSWORD") or "").strip()
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


@lru_cache(maxsize=1)
def get_redis():
    if redis is None:
        raise RuntimeError('Redis support requires: pip install "redis>=5.0"')
    if not redis_enabled():
        raise RuntimeError("REDIS_URL or REDIS_HOST is not configured.")
    client = redis.from_url(redis_url(), decode_responses=True)
    client.ping()
    logger.info(f"Redis connected ({redis_url().split('@')[-1]})")
    return client
