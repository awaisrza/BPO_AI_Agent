"""Call start/end hooks — Redis routing + Supabase persistence (transport only)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from .bot_context import BotRunContext
from .call_router import end_session, heartbeat_worker, start_session
from .supabase_calls import (
    create_call_record,
    duration_sec_from_started,
    finish_call_record,
    increment_bot_calls_today,
    outcome_from_end_reason,
    record_usage_minutes,
)


@dataclass
class ActiveCall:
    session_id: str
    call_id: str | None = None
    started_at: float = field(default_factory=time.time)
    phone: str | None = None
    vicidial_call_id: str | None = None
    transferred: bool = False


def begin_call(
    ctx: BotRunContext,
    *,
    session_id: str,
    phone: str | None = None,
    vicidial_call_id: str | None = None,
) -> ActiveCall:
    active = ActiveCall(
        session_id=session_id,
        phone=phone,
        vicidial_call_id=vicidial_call_id,
    )
    call_id: str | None = None
    try:
        call_id = create_call_record(
            org_id=ctx.org_id,
            campaign_id=_campaign_uuid(ctx),
            bot_id=ctx.bot_id,
            phone=phone,
        )
    except Exception as exc:
        logger.warning(f"Could not create Supabase call row: {exc}")
    active.call_id = call_id

    if ctx.bot_id:
        try:
            start_session(
                session_id,
                bot_id=ctx.bot_id,
                agent_user=ctx.agent_user,
                call_id=call_id,
                phone=phone,
                vicidial_call_id=vicidial_call_id,
            )
        except Exception as exc:
            logger.warning(f"Redis start_session failed: {exc}")
            try:
                heartbeat_worker(ctx.bot_id, ready=False)
            except Exception:
                pass
    return active


def complete_call(
    ctx: BotRunContext,
    active: ActiveCall | None,
    *,
    reason: str,
    transferred: bool | None = None,
) -> None:
    if active is None:
        return
    is_xfer = transferred if transferred is not None else active.transferred
    duration = duration_sec_from_started(active.started_at)
    outcome, disposition = outcome_from_end_reason(reason, transferred=is_xfer)

    if active.call_id:
        try:
            finish_call_record(
                active.call_id,
                duration_sec=duration,
                outcome=outcome,
                disposition=disposition,
                transferred=is_xfer,
            )
        except Exception as exc:
            logger.warning(f"Could not finish Supabase call row: {exc}")

    if ctx.bot_id:
        try:
            increment_bot_calls_today(ctx.bot_id)
        except Exception as exc:
            logger.warning(f"Could not increment calls_today: {exc}")

    try:
        record_usage_minutes(
            org_id=ctx.org_id,
            bot_id=ctx.bot_id,
            call_id=active.call_id,
            duration_sec=duration,
        )
    except Exception as exc:
        logger.warning(f"Could not record usage event: {exc}")

    try:
        end_session(active.session_id, reason=reason)
    except Exception as exc:
        logger.warning(f"Redis end_session failed: {exc}")
        if ctx.bot_id:
            try:
                heartbeat_worker(ctx.bot_id, ready=True)
            except Exception:
                pass


def mark_worker_ready(ctx: BotRunContext, *, ready: bool) -> None:
    if not ctx.bot_id:
        return
    try:
        heartbeat_worker(ctx.bot_id, ready=ready)
    except Exception as exc:
        logger.debug(f"Router heartbeat skipped: {exc}")


def _campaign_uuid(ctx: BotRunContext) -> str | None:
    return ctx.campaign_id
