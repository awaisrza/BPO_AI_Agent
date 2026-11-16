"""Redis-backed worker registry and call session routing."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .redis_client import get_redis, redis_enabled

_PREFIX = (os.getenv("CALL_ROUTER_KEY_PREFIX") or "aifronter").strip().rstrip(":")
_WORKER_TTL_SEC = int(os.getenv("CALL_ROUTER_WORKER_TTL_SEC", "120") or "120")
_SESSION_TTL_SEC = int(os.getenv("CALL_ROUTER_SESSION_TTL_SEC", "7200") or "7200")


def _worker_key(bot_id: str) -> str:
    return f"{_PREFIX}:worker:{bot_id}"


def _legacy_agent_key(agent_user: str) -> str:
    return f"{_PREFIX}:agent:{agent_user.strip()}"


def _tenant_agent_key(org_id: str, agent_user: str) -> str:
    return f"{_PREFIX}:tenant:{org_id.strip()}:{agent_user.strip()}"


def tenant_route_key(org_id: str, agent_user: str) -> str:
    """Stable lookup key for multi-tenant SIP routing."""
    return f"{org_id.strip()}:{agent_user.strip()}"


def _session_key(session_id: str) -> str:
    return f"{_PREFIX}:session:{session_id}"


@dataclass(frozen=True)
class WorkerRoute:
    bot_id: str
    agent_user: str
    media_port: int
    gpu_host: str
    org_id: str | None
    campaign_id: str | None
    ready: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "agent_user": self.agent_user,
            "media_port": self.media_port,
            "gpu_host": self.gpu_host,
            "org_id": self.org_id,
            "campaign_id": self.campaign_id,
            "ready": self.ready,
        }


def _now() -> float:
    return time.time()


def register_worker(
    *,
    bot_id: str,
    agent_user: str,
    media_port: int,
    gpu_host: str,
    org_id: str | None = None,
    campaign_id: str | None = None,
    ready: bool = True,
) -> None:
    if not redis_enabled():
        return
    payload = {
        "bot_id": bot_id,
        "agent_user": agent_user.strip(),
        "media_port": int(media_port),
        "gpu_host": gpu_host.strip(),
        "org_id": org_id,
        "campaign_id": campaign_id,
        "ready": ready,
        "updated_at": _now(),
    }
    r = get_redis()
    pipe = r.pipeline()
    pipe.set(_worker_key(bot_id), json.dumps(payload), ex=_WORKER_TTL_SEC)
    agent_user = agent_user.strip()
    if org_id:
        pipe.set(_tenant_agent_key(org_id, agent_user), bot_id, ex=_WORKER_TTL_SEC)
    else:
        pipe.set(_legacy_agent_key(agent_user), bot_id, ex=_WORKER_TTL_SEC)
    pipe.execute()
    scope = tenant_route_key(org_id, agent_user) if org_id else agent_user
    logger.debug(f"Router registered worker {scope} -> {gpu_host}:{media_port}")


def heartbeat_worker(bot_id: str, *, ready: bool) -> None:
    if not redis_enabled():
        return
    r = get_redis()
    raw = r.get(_worker_key(bot_id))
    if not raw:
        return
    data = json.loads(raw)
    data["ready"] = ready
    data["updated_at"] = _now()
    r.set(_worker_key(bot_id), json.dumps(data), ex=_WORKER_TTL_SEC)
    agent_user = (data.get("agent_user") or "").strip()
    org_id = (data.get("org_id") or "").strip() or None
    if agent_user:
        if org_id:
            r.set(_tenant_agent_key(org_id, agent_user), bot_id, ex=_WORKER_TTL_SEC)
        else:
            r.set(_legacy_agent_key(agent_user), bot_id, ex=_WORKER_TTL_SEC)


def unregister_worker(
    bot_id: str,
    *,
    agent_user: str | None = None,
    org_id: str | None = None,
) -> None:
    if not redis_enabled():
        return
    r = get_redis()
    org_from_worker: str | None = org_id
    if not agent_user or not org_from_worker:
        raw = r.get(_worker_key(bot_id))
        if raw:
            data = json.loads(raw)
            agent_user = agent_user or (data.get("agent_user") or "").strip() or None
            org_from_worker = org_from_worker or (data.get("org_id") or "").strip() or None
    pipe = r.pipeline()
    pipe.delete(_worker_key(bot_id))
    if agent_user:
        if org_from_worker:
            pipe.delete(_tenant_agent_key(org_from_worker, agent_user))
        else:
            pipe.delete(_legacy_agent_key(agent_user))
    pipe.execute()


def resolve_agent(agent_user: str, org_id: str | None = None) -> WorkerRoute | None:
    if not redis_enabled():
        return None
    r = get_redis()
    bot_id: str | None = None
    agent_user = agent_user.strip()
    if org_id:
        bot_id = r.get(_tenant_agent_key(org_id, agent_user))
    if not bot_id:
        bot_id = r.get(_legacy_agent_key(agent_user))
    if not bot_id:
        return None
    raw = r.get(_worker_key(bot_id))
    if not raw:
        return None
    data = json.loads(raw)
    return WorkerRoute(
        bot_id=data["bot_id"],
        agent_user=data["agent_user"],
        media_port=int(data["media_port"]),
        gpu_host=data["gpu_host"],
        org_id=data.get("org_id"),
        campaign_id=data.get("campaign_id"),
        ready=bool(data.get("ready")),
    )


def list_workers() -> list[dict[str, Any]]:
    if not redis_enabled():
        return []
    r = get_redis()
    workers: list[dict[str, Any]] = []
    for key in r.scan_iter(match=f"{_PREFIX}:worker:*"):
        raw = r.get(key)
        if not raw:
            continue
        data = json.loads(raw)
        workers.append(data)
    workers.sort(key=lambda row: row.get("agent_user") or "")
    return workers


def start_session(
    session_id: str,
    *,
    bot_id: str,
    agent_user: str,
    call_id: str | None = None,
    phone: str | None = None,
    vicidial_call_id: str | None = None,
) -> None:
    if not redis_enabled():
        return
    payload = {
        "session_id": session_id,
        "bot_id": bot_id,
        "agent_user": agent_user,
        "call_id": call_id,
        "phone": phone,
        "vicidial_call_id": vicidial_call_id,
        "started_at": _now(),
        "status": "live",
    }
    r = get_redis()
    r.set(_session_key(session_id), json.dumps(payload), ex=_SESSION_TTL_SEC)
    heartbeat_worker(bot_id, ready=False)


def end_session(session_id: str, *, reason: str) -> dict[str, Any] | None:
    if not redis_enabled():
        return None
    r = get_redis()
    key = _session_key(session_id)
    raw = r.get(key)
    if not raw:
        return None
    data = json.loads(raw)
    data["status"] = "ended"
    data["ended_at"] = _now()
    data["end_reason"] = reason
    r.set(key, json.dumps(data), ex=_SESSION_TTL_SEC)
    bot_id = data.get("bot_id")
    if bot_id:
        heartbeat_worker(str(bot_id), ready=True)
    return data


def router_status() -> dict[str, Any]:
    workers = list_workers()
    ready = sum(1 for w in workers if w.get("ready"))
    return {
        "enabled": redis_enabled(),
        "workers": workers,
        "worker_count": len(workers),
        "ready_count": ready,
        "busy_count": len(workers) - ready,
    }
