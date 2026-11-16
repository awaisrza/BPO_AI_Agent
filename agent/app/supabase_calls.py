"""Persist call records to Supabase (service role — bypasses RLS)."""

from __future__ import annotations

import math
from typing import Any

import httpx
from loguru import logger

from .supabase_client import supabase_config, supabase_headers


def create_call_record(
    *,
    org_id: str | None,
    campaign_id: str | None,
    bot_id: str | None,
    phone: str | None,
) -> str | None:
    if not org_id:
        logger.warning("Skipping call record — bot/campaign has no org_id")
        return None
    base, key = supabase_config()
    url = f"{base}/rest/v1/calls"
    payload: dict[str, Any] = {
        "org_id": org_id,
        "campaign_id": campaign_id,
        "bot_id": bot_id,
        "phone": phone or "",
        "duration_sec": 0,
        "outcome": "in_progress",
        "disposition": None,
        "transferred": False,
        "transcript_json": [],
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            url,
            headers={
                **supabase_headers(key),
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
        )
        resp.raise_for_status()
        rows = resp.json()
    if not rows:
        return None
    call_id = rows[0].get("id")
    logger.info(f"Created call record {call_id} for bot {bot_id}")
    return call_id


def finish_call_record(
    call_id: str,
    *,
    duration_sec: int,
    outcome: str,
    disposition: str | None = None,
    transferred: bool = False,
    transcript_json: list[dict[str, Any]] | None = None,
) -> None:
    base, key = supabase_config()
    url = f"{base}/rest/v1/calls"
    params = {"id": f"eq.{call_id}"}
    payload: dict[str, Any] = {
        "duration_sec": max(0, duration_sec),
        "outcome": outcome,
        "disposition": disposition,
        "transferred": transferred,
    }
    if transcript_json is not None:
        payload["transcript_json"] = transcript_json
    with httpx.Client(timeout=20.0) as client:
        resp = client.patch(
            url,
            params=params,
            headers={
                **supabase_headers(key),
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
        )
        resp.raise_for_status()
    logger.info(f"Finished call {call_id}: {outcome} ({duration_sec}s)")


def increment_bot_calls_today(bot_id: str) -> None:
    base, key = supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {"id": f"eq.{bot_id}", "select": "calls_today"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return
        current = int(rows[0].get("calls_today") or 0)
        patch = client.patch(
            url,
            params={"id": f"eq.{bot_id}"},
            headers={
                **supabase_headers(key),
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={"calls_today": current + 1},
        )
        patch.raise_for_status()


def record_usage_minutes(
    *,
    org_id: str | None,
    bot_id: str | None,
    call_id: str | None,
    duration_sec: int,
) -> None:
    if not org_id or duration_sec <= 0:
        return
    minutes = round(duration_sec / 60.0, 2)
    if minutes <= 0:
        minutes = round(max(duration_sec, 1) / 60.0, 2)
    base, key = supabase_config()
    url = f"{base}/rest/v1/usage_events"
    payload = {
        "org_id": org_id,
        "bot_id": bot_id,
        "call_id": call_id,
        "minutes": minutes,
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            url,
            headers={
                **supabase_headers(key),
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
        )
        resp.raise_for_status()


def outcome_from_end_reason(reason: str, *, transferred: bool = False) -> tuple[str, str | None]:
    if transferred:
        return "transferred", "XFER"
    mapping = {
        "idle_timeout": ("no_answer", "TIMEOT"),
        "remote_hangup": ("hangup", "HU"),
        "greeting_startup_timeout": ("no_connect", "NA"),
        "runner_finished": ("completed", None),
        "exception": ("error", "ER"),
    }
    outcome, disposition = mapping.get(reason, ("ended", reason.upper()[:8]))
    return outcome, disposition


def duration_sec_from_started(started_at: float | None) -> int:
    if not started_at:
        return 0
    import time

    return max(0, int(math.ceil(time.time() - started_at)))
