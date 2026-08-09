"""GPU fleet supervisor — watches Supabase for running campaigns and manages agent workers."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from loguru import logger

from .config import settings
from .supabase_client import supabase_config, supabase_headers

_AGENT_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = sys.executable
_SUPERVISOR_SECRET = os.getenv("GPU_SUPERVISOR_SECRET", "").strip()
_POLL_SEC = float(os.getenv("FLEET_POLL_SEC", "20") or "20")
_MAX_WORKERS = int(os.getenv("FLEET_MAX_WORKERS", "3") or "3")
_MEDIA_BASE_PORT = int(os.getenv("FLEET_MEDIA_BASE_PORT", "8800") or "8800")
_INFERENCE_POOL_PORT = int(os.getenv("INFERENCE_POOL_PORT", "8780") or "8780")
_INFERENCE_POOL_HOST = os.getenv("INFERENCE_POOL_HOST", "127.0.0.1").strip() or "127.0.0.1"
_INFERENCE_POOL_URL = (
    os.getenv("INFERENCE_POOL_URL", "").strip()
    or f"http://{_INFERENCE_POOL_HOST}:{_INFERENCE_POOL_PORT}"
)
_INFERENCE_POOL_ENABLED = os.getenv("INFERENCE_POOL_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}


@dataclass
class PoolRecord:
    process: subprocess.Popen[Any]
    started_at: float = field(default_factory=time.time)


@dataclass
class WorkerRecord:
    bot_id: str
    campaign_id: str
    org_id: str | None
    vicidial_agent_user: str
    vicidial_campaign_id: str | None
    media_port: int
    process: subprocess.Popen[Any]
    started_at: float = field(default_factory=time.time)


class FleetSupervisor:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerRecord] = {}
        self._pool: PoolRecord | None = None
        self._last_sync: float = 0.0
        self._last_error: str | None = None

    def _pool_health(self) -> dict[str, Any] | None:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{_INFERENCE_POOL_URL.rstrip('/')}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    def _ensure_inference_pool(self) -> None:
        if not _INFERENCE_POOL_ENABLED:
            return
        health = self._pool_health()
        if health and health.get("ok"):
            return
        if self._pool and self._pool.process.poll() is None:
            return

        cmd = [_PYTHON, "-m", "app.inference_pool"]
        env = os.environ.copy()
        env.setdefault("INFERENCE_POOL_HOST", _INFERENCE_POOL_HOST)
        env.setdefault("INFERENCE_POOL_PORT", str(_INFERENCE_POOL_PORT))
        env.setdefault("INFERENCE_POOL_URL", _INFERENCE_POOL_URL)
        log_path = Path("/tmp/inference_pool.log")
        log_fh = open(log_path, "a", encoding="utf-8")
        logger.info(f"Starting inference pool: {' '.join(cmd)} (log={log_path})")
        proc = subprocess.Popen(
            cmd,
            cwd=str(_AGENT_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._pool = PoolRecord(process=proc)

        deadline = time.monotonic() + 180.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("Inference pool process exited during startup")
            health = self._pool_health()
            if health and health.get("ok"):
                logger.info(
                    f"Inference pool ready at {_INFERENCE_POOL_URL} "
                    f"(cache={health.get('cache_size', 0)})"
                )
                return
            time.sleep(2.0)
        raise RuntimeError(f"Inference pool at {_INFERENCE_POOL_URL} did not become ready")

    def _stop_inference_pool(self) -> None:
        record = self._pool
        self._pool = None
        if not record:
            return
        proc = record.process
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        logger.info("Stopped inference pool")

    def _fetch_running_bots(self, campaign_id: str | None = None) -> list[dict[str, str]]:
        base, key = supabase_config()
        with httpx.Client(timeout=20.0) as client:
            campaign_params: dict[str, str] = {"select": "id,vicidial_campaign_id", "status": "eq.running"}
            if campaign_id:
                campaign_params["id"] = f"eq.{campaign_id}"
            camp_resp = client.get(
                f"{base}/rest/v1/campaigns",
                params=campaign_params,
                headers=supabase_headers(key),
            )
            camp_resp.raise_for_status()
            campaigns = camp_resp.json()
            if not campaigns:
                return []

            running_ids = [row["id"] for row in campaigns if row.get("id")]
            campaign_vd = {
                row["id"]: (row.get("vicidial_campaign_id") or "").strip() or None for row in campaigns
            }

            in_list = ",".join(running_ids)
            bot_resp = client.get(
                f"{base}/rest/v1/bots",
                params={
                    "select": "id,name,campaign_id,vicidial_agent_user,org_id",
                    "campaign_id": f"in.({in_list})",
                },
                headers=supabase_headers(key),
            )
            bot_resp.raise_for_status()
            rows = bot_resp.json()

        bots: list[dict[str, str]] = []
        for row in rows:
            bot_id = row.get("id")
            cid = row.get("campaign_id")
            if bot_id and cid:
                bots.append(
                    {
                        "id": bot_id,
                        "name": row.get("name") or bot_id,
                        "campaign_id": cid,
                        "vicidial_agent_user": (row.get("vicidial_agent_user") or "").strip(),
                        "vicidial_campaign_id": campaign_vd.get(cid) or "",
                        "org_id": (row.get("org_id") or "").strip() or "",
                    }
                )
        return bots[:_MAX_WORKERS]

    def _next_media_port(self) -> int:
        used = {rec.media_port for rec in self._workers.values()}
        for offset in range(_MAX_WORKERS):
            port = _MEDIA_BASE_PORT + offset
            if port not in used:
                return port
        return _MEDIA_BASE_PORT + len(self._workers)

    def _spawn_worker(self, bot: dict[str, str]) -> WorkerRecord:
        bot_id = bot["id"]
        media_port = self._next_media_port()
        cmd = [_PYTHON, "-m", "app.fleet_worker", bot_id]
        env = os.environ.copy()
        env["FLEET_WORKER_MEDIA_PORT"] = str(media_port)
        if _INFERENCE_POOL_ENABLED:
            env.setdefault("INFERENCE_POOL_URL", _INFERENCE_POOL_URL)
        logger.info(
            f"Starting worker: {' '.join(cmd)} "
            f"(ViciDial user={bot.get('vicidial_agent_user')}, media port={media_port})"
        )
        # Log to a file — PIPE without a reader fills and can hang/kill the worker.
        log_path = Path(f"/tmp/fleet_worker_{bot_id[:8]}.log")
        log_fh = open(log_path, "a", encoding="utf-8")
        logger.info(f"Worker log: {log_path}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(_AGENT_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return WorkerRecord(
            bot_id=bot_id,
            campaign_id=bot["campaign_id"],
            org_id=(bot.get("org_id") or "").strip() or None,
            vicidial_agent_user=bot.get("vicidial_agent_user") or "",
            vicidial_campaign_id=bot.get("vicidial_campaign_id") or None,
            media_port=media_port,
            process=proc,
        )

    def _stop_worker(self, bot_id: str) -> None:
        record = self._workers.pop(bot_id, None)
        if not record:
            return
        proc = record.process
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        logger.info(f"Stopped worker for bot {bot_id}")

    def _reap_dead_workers(self) -> None:
        dead = [bot_id for bot_id, rec in self._workers.items() if rec.process.poll() is not None]
        for bot_id in dead:
            logger.warning(f"Worker exited for bot {bot_id}")
            self._workers.pop(bot_id, None)

    def _worker_media_health(self, media_port: int) -> dict[str, Any]:
        url = f"http://127.0.0.1:{media_port}/health"
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"reachable": False, "ready": False, "url": url}
                body = resp.json()
                ready = body.get("ready") is True or str(body.get("ready", "")).lower() == "true"
                return {"reachable": True, "ready": ready, "url": url, "body": body}
        except Exception as exc:
            return {"reachable": False, "ready": False, "url": url, "error": str(exc)}

    def _read_worker_log_tail(self, bot_id: str, lines: int = 40) -> list[str]:
        path = Path(f"/tmp/fleet_worker_{bot_id[:8]}.log")
        if not path.is_file():
            return []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        rows = content.splitlines()
        return rows[-lines:] if len(rows) > lines else rows

    def sync(self, campaign_id: str | None = None) -> dict[str, Any]:
        self._reap_dead_workers()
        try:
            if _INFERENCE_POOL_ENABLED:
                self._ensure_inference_pool()
            desired = self._fetch_running_bots(campaign_id)
            desired_ids = {b["id"] for b in desired}
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"Sync failed: {exc}")
            return self.status()

        for bot_id in list(self._workers):
            if bot_id not in desired_ids:
                self._stop_worker(bot_id)

        for bot in desired:
            bot_id = bot["id"]
            if bot_id in self._workers:
                continue
            if len(self._workers) >= _MAX_WORKERS:
                logger.warning(f"Max workers ({_MAX_WORKERS}) reached — skipping bot {bot_id}")
                continue
            if not bot.get("vicidial_agent_user"):
                logger.warning(f"Bot {bot_id} missing vicidial_agent_user — skipping")
                continue
            self._workers[bot_id] = self._spawn_worker(bot)

        self._last_sync = time.time()
        return self.status()

    def stop_campaign(self, campaign_id: str) -> dict[str, Any]:
        for bot_id, rec in list(self._workers.items()):
            if rec.campaign_id == campaign_id:
                self._stop_worker(bot_id)
        if not self._workers:
            self._stop_inference_pool()
        self._last_sync = time.time()
        return self.status()

    def status(self) -> dict[str, Any]:
        self._reap_dead_workers()
        workers = []
        for bot_id, rec in self._workers.items():
            workers.append(
                {
                    "bot_id": bot_id,
                    "campaign_id": rec.campaign_id,
                    "vicidial_agent_user": rec.vicidial_agent_user,
                    "vicidial_campaign_id": rec.vicidial_campaign_id,
                    "org_id": rec.org_id,
                    "media_port": rec.media_port,
                    "pid": rec.process.pid,
                    "running": rec.process.poll() is None,
                    "uptime_sec": int(time.time() - rec.started_at),
                    "media_health": self._worker_media_health(rec.media_port),
                }
            )
        return {
            "ok": self._last_error is None,
            "error": self._last_error,
            "inference_pool": {
                "enabled": _INFERENCE_POOL_ENABLED,
                "url": _INFERENCE_POOL_URL if _INFERENCE_POOL_ENABLED else None,
                "running": self._pool.process.poll() is None if self._pool else False,
                "health": self._pool_health() if _INFERENCE_POOL_ENABLED else None,
            },
            "workers": workers,
            "worker_count": len(workers),
            "max_workers": _MAX_WORKERS,
            "last_sync_at": self._last_sync or None,
        }


supervisor = FleetSupervisor()


def _check_auth(authorization: str | None, x_supervisor_secret: str | None) -> None:
    if not _SUPERVISOR_SECRET:
        return
    token = (authorization or "").removeprefix("Bearer ").strip() or (x_supervisor_secret or "").strip()
    if token != _SUPERVISOR_SECRET:
        raise HTTPException(status_code=401, detail="Invalid supervisor secret.")


def build_app() -> FastAPI:
    app = FastAPI(title="AI Fronter Fleet Supervisor", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    def status(
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization, x_supervisor_secret)
        return supervisor.status()

    @app.get("/logs/worker")
    def worker_logs(
        bot_id: str = Query(..., min_length=8),
        lines: int = Query(default=40, ge=1, le=200),
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization, x_supervisor_secret)
        tail = supervisor._read_worker_log_tail(bot_id.strip(), lines)
        return {
            "ok": True,
            "bot_id": bot_id.strip(),
            "lines": tail,
            "path": f"/tmp/fleet_worker_{bot_id.strip()[:8]}.log",
        }

    @app.post("/sync")
    def sync(
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
        campaign_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization, x_supervisor_secret)
        return supervisor.sync(campaign_id)

    @app.post("/stop")
    def stop(
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
        campaign_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization, x_supervisor_secret)
        if campaign_id:
            return supervisor.stop_campaign(campaign_id)
        for bot_id in list(supervisor._workers):
            supervisor._stop_worker(bot_id)
        supervisor._stop_inference_pool()
        return supervisor.status()

    @app.get("/route")
    def route_call(
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
        agent_user: str = Query(..., min_length=1),
        org_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Resolve ViciDial agent user → GPU worker media endpoint (Redis or live supervisor)."""
        _check_auth(authorization, x_supervisor_secret)
        from .call_router import resolve_agent, router_status

        route = resolve_agent(agent_user, org_id=org_id)
        if route is not None:
            return {"ok": True, "source": "redis", **route.as_dict()}

        for worker in supervisor.status().get("workers", []):
            if worker.get("vicidial_agent_user") != agent_user.strip():
                continue
            if org_id and worker.get("org_id") and worker.get("org_id") != org_id.strip():
                continue
            gpu_host = (
                os.getenv("GPU_PUBLIC_HOST")
                or os.getenv("FLEET_GPU_PUBLIC_HOST")
                or "127.0.0.1"
            )
            return {
                "ok": True,
                "source": "supervisor",
                "bot_id": worker.get("bot_id"),
                "agent_user": agent_user.strip(),
                "org_id": worker.get("org_id") or org_id,
                "media_port": worker.get("media_port"),
                "gpu_host": gpu_host,
                "ready": worker.get("running", False),
            }

        scope = f"{org_id}:{agent_user}" if org_id else agent_user
        return {
            "ok": False,
            "error": f"No worker registered for ViciDial agent {scope}",
            "router": router_status(),
        }

    @app.get("/router/status")
    def router_status_endpoint(
        authorization: str | None = Header(default=None),
        x_supervisor_secret: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _check_auth(authorization, x_supervisor_secret)
        from .call_router import router_status

        body = router_status()
        body["supervisor_workers"] = supervisor.status().get("workers", [])
        return body

    return app


async def poll_loop() -> None:
    while True:
        try:
            supervisor.sync()
        except Exception as exc:
            logger.error(f"Poll sync error: {exc}")
        await asyncio.sleep(_POLL_SEC)


def run_supervisor(host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SystemExit(
            "Fleet supervisor needs NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local"
        )

    bind_host = host or os.getenv("SUPERVISOR_HOST", "0.0.0.0")
    bind_port = port or int(os.getenv("SUPERVISOR_PORT", "8770") or "8770")
    app = build_app()

    @app.on_event("startup")
    async def _startup() -> None:
        asyncio.create_task(poll_loop())
        supervisor.sync()
        logger.info(f"Fleet supervisor listening on {bind_host}:{bind_port}")

    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")
