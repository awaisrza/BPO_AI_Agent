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


@dataclass
class WorkerRecord:
    bot_id: str
    campaign_id: str
    vicidial_agent_user: str
    vicidial_campaign_id: str | None
    process: subprocess.Popen[Any]
    started_at: float = field(default_factory=time.time)


class FleetSupervisor:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerRecord] = {}
        self._last_sync: float = 0.0
        self._last_error: str | None = None

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
                    "select": "id,name,campaign_id,vicidial_agent_user",
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
                    }
                )
        return bots[:_MAX_WORKERS]

    def _spawn_worker(self, bot: dict[str, str]) -> WorkerRecord:
        bot_id = bot["id"]
        cmd = [_PYTHON, "-m", "app.fleet_worker", bot_id]
        logger.info(f"Starting worker: {' '.join(cmd)} (ViciDial user={bot.get('vicidial_agent_user')})")
        proc = subprocess.Popen(
            cmd,
            cwd=str(_AGENT_ROOT),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return WorkerRecord(
            bot_id=bot_id,
            campaign_id=bot["campaign_id"],
            vicidial_agent_user=bot.get("vicidial_agent_user") or "",
            vicidial_campaign_id=bot.get("vicidial_campaign_id") or None,
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

    def sync(self, campaign_id: str | None = None) -> dict[str, Any]:
        self._reap_dead_workers()
        try:
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
                    "pid": rec.process.pid,
                    "running": rec.process.poll() is None,
                    "uptime_sec": int(time.time() - rec.started_at),
                }
            )
        return {
            "ok": self._last_error is None,
            "error": self._last_error,
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
        return supervisor.status()

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
