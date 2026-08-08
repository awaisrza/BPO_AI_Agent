"""Multi-tenant call router and SIP telephony helper tests."""

from __future__ import annotations

import pytest


def test_tenant_agent_isolation(redis_client):
    from app.call_router import register_worker, resolve_agent, unregister_worker

    register_worker(
        bot_id="bot-a",
        agent_user="6666",
        media_port=8800,
        gpu_host="10.0.0.1",
        org_id="org-a",
        ready=True,
    )
    register_worker(
        bot_id="bot-b",
        agent_user="6666",
        media_port=8801,
        gpu_host="10.0.0.2",
        org_id="org-b",
        ready=True,
    )

    route_a = resolve_agent("6666", org_id="org-a")
    route_b = resolve_agent("6666", org_id="org-b")
    assert route_a is not None
    assert route_b is not None
    assert route_a.bot_id == "bot-a"
    assert route_b.bot_id == "bot-b"
    assert route_a.media_port == 8800
    assert route_b.media_port == 8801

    assert resolve_agent("6666") is None

    unregister_worker("bot-a", agent_user="6666", org_id="org-a")
    unregister_worker("bot-b", agent_user="6666", org_id="org-b")


def test_legacy_agent_key_without_org(redis_client):
    from app.call_router import register_worker, resolve_agent, unregister_worker

    register_worker(
        bot_id="bot-legacy",
        agent_user="8888",
        media_port=8802,
        gpu_host="10.0.0.3",
        ready=True,
    )
    route = resolve_agent("8888")
    assert route is not None
    assert route.bot_id == "bot-legacy"
    unregister_worker("bot-legacy", agent_user="8888")


def test_parse_sip_uri():
    from app.sip_telephony import build_sip_uri, parse_sip_user_host, slugify_org_name

    assert slugify_org_name("Acme Corp!") == "acme-corp"
    user, slug = parse_sip_user_host("sip:6666@acme-corp.bots.example.com")
    assert user == "6666"
    assert slug == "acme-corp"
    uri = build_sip_uri("6666", org_ref="org-uuid", domain="bots.example.com")
    assert uri == "sip:6666@org-uuid.bots.example.com"


def test_media_message_roundtrip():
    import base64

    from app.sip_telephony import decode_media_payload, media_message, ulaw_silence_chunk

    pcmu = ulaw_silence_chunk()
    msg = media_message(base64.b64encode(pcmu).decode("ascii"))
    assert decode_media_payload(msg) == pcmu


def test_resolve_worker_route_redis(monkeypatch, redis_client):
    from app.call_router import register_worker
    from app.sip_edge.router import resolve_worker_route

    register_worker(
        bot_id="bot-x",
        agent_user="7777",
        media_port=8803,
        gpu_host="10.0.0.9",
        org_id="org-x",
        ready=True,
    )
    body = resolve_worker_route("7777", org_id="org-x")
    assert body["ok"] is True
    assert body["media_port"] == 8803


@pytest.mark.asyncio
async def test_sip_edge_route_endpoint(monkeypatch, redis_client):
    pytest.importorskip("fastapi")
    from app.call_router import register_worker
    from app.sip_edge.server import build_app
    from fastapi.testclient import TestClient

    register_worker(
        bot_id="bot-y",
        agent_user="5555",
        media_port=8804,
        gpu_host="10.0.0.10",
        org_id="org-y",
        ready=True,
    )
    app = build_app()
    with TestClient(app) as client:
        resp = client.get("/v1/route", params={"agent_user": "5555", "org_id": "org-y"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
