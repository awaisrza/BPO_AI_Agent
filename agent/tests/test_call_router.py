"""Tests for Redis call router (uses fakeredis when available)."""

from __future__ import annotations

import pytest


def test_register_and_resolve_agent(redis_client):
    from app.call_router import register_worker, resolve_agent, unregister_worker

    register_worker(
        bot_id="bot-1",
        agent_user="6666",
        media_port=8800,
        gpu_host="10.0.0.1",
        org_id="org-1",
        campaign_id="camp-1",
        ready=True,
    )
    route = resolve_agent("6666", org_id="org-1")
    assert route is not None
    assert route.media_port == 8800
    assert route.gpu_host == "10.0.0.1"
    assert route.ready is True

    unregister_worker("bot-1", agent_user="6666", org_id="org-1")
    assert resolve_agent("6666", org_id="org-1") is None


def test_session_marks_worker_busy_then_ready(redis_client):
    from app.call_router import heartbeat_worker, register_worker, resolve_agent, start_session, end_session

    register_worker(
        bot_id="bot-2",
        agent_user="7777",
        media_port=8801,
        gpu_host="10.0.0.2",
        ready=True,
    )
    start_session("sess-1", bot_id="bot-2", agent_user="7777", phone="+15551212")
    route = resolve_agent("7777")
    assert route is not None
    assert route.ready is False

    end_session("sess-1", reason="remote_hangup")
    route = resolve_agent("7777")
    assert route is not None
    assert route.ready is True


def test_outcome_mapping():
    from app.supabase_calls import outcome_from_end_reason

    outcome, disp = outcome_from_end_reason("idle_timeout")
    assert outcome == "no_answer"
    assert disp == "TIMEOT"

    outcome, disp = outcome_from_end_reason("anything", transferred=True)
    assert outcome == "transferred"
    assert disp == "XFER"
