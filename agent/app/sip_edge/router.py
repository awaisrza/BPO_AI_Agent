"""Resolve SIP tenant/agent identifiers to GPU worker routes."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from loguru import logger

from ..call_router import resolve_agent
from ..sip_telephony import parse_sip_user_host, slugify_org_name

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def sip_edge_domain() -> str:
    return os.getenv("SIP_EDGE_DOMAIN", "bots.example.com").strip() or "bots.example.com"


def resolve_org_id_from_subdomain(subdomain: str) -> str | None:
    """Map SIP subdomain to org_id (UUID or slug lookup)."""
    token = subdomain.strip()
    if not token:
        return None
    if _UUID_RE.match(token):
        return token
    override = os.getenv(f"SIP_ORG_SLUG_{token.upper()}", "").strip()
    if override:
        return override
    slug_map_raw = os.getenv("SIP_ORG_SLUG_MAP", "").strip()
    if slug_map_raw:
        for pair in slug_map_raw.split(","):
            slug, _, org_id = pair.partition("=")
            if slug.strip().lower() == token.lower() and org_id.strip():
                return org_id.strip()
    try:
        from ..supabase_client import supabase_config, supabase_headers

        base, key = supabase_config()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{base}/rest/v1/organizations",
                params={"select": "id,name"},
                headers=supabase_headers(key),
            )
            resp.raise_for_status()
            for row in resp.json():
                name = str(row.get("name") or "")
                if slugify_org_name(name) == token.lower():
                    return str(row.get("id"))
    except Exception as exc:
        logger.debug(f"Supabase org slug lookup skipped: {exc}")
    return None


def parse_inbound_sip_target(
    *,
    sip_uri: str | None = None,
    agent_user: str | None = None,
    org_id: str | None = None,
    org_slug: str | None = None,
) -> tuple[str, str | None]:
    """Normalize routing inputs to (agent_user, org_id)."""
    if sip_uri:
        user, subdomain = parse_sip_user_host(sip_uri)
        resolved_org = resolve_org_id_from_subdomain(subdomain)
        return user, org_id or resolved_org
    if not agent_user:
        raise ValueError("agent_user or sip_uri is required")
    if org_id:
        return agent_user.strip(), org_id.strip()
    if org_slug:
        resolved = resolve_org_id_from_subdomain(org_slug)
        return agent_user.strip(), resolved
    return agent_user.strip(), None


def fetch_supervisor_route(
    agent_user: str,
    *,
    org_id: str | None = None,
) -> dict[str, Any] | None:
    base = (
        os.getenv("GPU_SUPERVISOR_URL")
        or os.getenv("SIP_EDGE_GPU_SUPERVISOR_URL")
        or ""
    ).strip().rstrip("/")
    if not base:
        host = os.getenv("GPU_PUBLIC_HOST", "127.0.0.1")
        port = os.getenv("SUPERVISOR_PORT", "8770")
        base = f"http://{host}:{port}"
    params: dict[str, str] = {"agent_user": agent_user.strip()}
    if org_id:
        params["org_id"] = org_id.strip()
    headers: dict[str, str] = {"Accept": "application/json"}
    secret = os.getenv("GPU_SUPERVISOR_SECRET", "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(f"{base}/route", params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            if body.get("ok"):
                return body
    except Exception as exc:
        logger.debug(f"Supervisor route lookup failed: {exc}")
    return None


def resolve_worker_route(
    agent_user: str,
    *,
    org_id: str | None = None,
) -> dict[str, Any]:
    route = resolve_agent(agent_user, org_id=org_id)
    if route is not None:
        return {"ok": True, "source": "redis", **route.as_dict()}

    supervisor = fetch_supervisor_route(agent_user, org_id=org_id)
    if supervisor is not None:
        return supervisor

    scope = f"{org_id}:{agent_user}" if org_id else agent_user
    return {
        "ok": False,
        "error": f"No worker registered for {scope}",
    }
