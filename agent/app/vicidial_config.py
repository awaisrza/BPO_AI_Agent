"""Load organization ViciDial credentials from Supabase."""

from __future__ import annotations

from typing import Any

import httpx

from .bot_context import VicidialOrgConfig
from .supabase_client import ScriptLoadError, supabase_config, supabase_headers


def load_vicidial_for_org(org_id: str) -> VicidialOrgConfig | None:
    base, key = supabase_config()
    url = f"{base}/rest/v1/organizations"
    params = {
        "id": f"eq.{org_id}",
        "select": "vicidial_url,vicidial_user,vicidial_pass,transfer_preset",
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        return None

    row: dict[str, Any] = rows[0]
    dial_url = (row.get("vicidial_url") or "").strip()
    dial_user = (row.get("vicidial_user") or "").strip()
    dial_pass = (row.get("vicidial_pass") or "").strip()
    if not dial_url or not dial_user or not dial_pass:
        return None

    return VicidialOrgConfig(
        base_url=dial_url.rstrip("/"),
        api_user=dial_user,
        api_pass=dial_pass,
        transfer_preset=(row.get("transfer_preset") or "CLOSER").strip() or "CLOSER",
    )


def load_vicidial_from_env_fallback() -> VicidialOrgConfig | None:
    from .config import settings

    if not settings.vicidial_base_url or not settings.vicidial_user or not settings.vicidial_pass:
        return None
    return VicidialOrgConfig(
        base_url=settings.vicidial_base_url.rstrip("/"),
        api_user=settings.vicidial_user,
        api_pass=settings.vicidial_pass,
        transfer_preset=settings.vicidial_transfer_preset or "CLOSER",
    )


def resolve_vicidial_config(org_id: str | None) -> VicidialOrgConfig | None:
    if org_id:
        try:
            cfg = load_vicidial_for_org(org_id)
            if cfg:
                return cfg
        except Exception as exc:
            raise ScriptLoadError(f"Could not load ViciDial credentials for org {org_id}: {exc}") from exc
    return load_vicidial_from_env_fallback()
