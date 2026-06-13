"""Load campaign scripts from Supabase (dashboard → agent)."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from .config import ScriptConfig, settings


class ScriptLoadError(RuntimeError):
    pass


def _supabase_config() -> tuple[str, str]:
    url = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_service_role_key
    if not url or not key:
        raise ScriptLoadError(
            "Supabase not configured for the agent. Add to dashboard/.env.local or agent/.env:\n"
            "  NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co\n"
            "  SUPABASE_SERVICE_ROLE_KEY=your-service-role-key\n"
            "(Project Settings → API → service_role — keep secret, never commit)"
        )
    return url, key


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _parse_script_json(data: dict[str, Any], *, source: str) -> ScriptConfig:
    if not data.get("greeting") or not data.get("pitch"):
        raise ScriptLoadError(f"Campaign script at {source} is missing greeting or pitch.")
    script = ScriptConfig.from_script_json(data)
    logger.info(
        f"Loaded script from Supabase ({source}): "
        f"{len(script.qualifying_questions)} qualifying question(s)"
    )
    return script


def load_script_for_campaign(campaign_id: str) -> ScriptConfig:
    """Load script_json for a campaign UUID."""
    base, key = _supabase_config()
    url = f"{base}/rest/v1/campaigns"
    params = {"id": f"eq.{campaign_id}", "select": "id,name,script_json"}

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params, headers=_headers(key))
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        raise ScriptLoadError(f"No campaign found with id={campaign_id}")

    row = rows[0]
    name = row.get("name") or campaign_id
    script_json = row.get("script_json") or {}
    return _parse_script_json(script_json, source=f"campaign '{name}'")


def load_script_for_bot(bot_id: str) -> tuple[ScriptConfig, str]:
    """Load script via bot → assigned campaign. Returns (script, bot_name)."""
    base, key = _supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {
        "id": f"eq.{bot_id}",
        "select": "id,name,campaign_id,campaigns(script_json,name)",
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params, headers=_headers(key))
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        raise ScriptLoadError(f"No bot found with id={bot_id}")

    bot = rows[0]
    bot_name = bot.get("name") or bot_id
    campaign = bot.get("campaigns")
    if not campaign:
        raise ScriptLoadError(
            f"Bot '{bot_name}' has no campaign assigned. "
            "Assign it in Dashboard → Bots → Assign to campaign."
        )

    campaign_name = campaign.get("name") or bot.get("campaign_id")
    script_json = campaign.get("script_json") or {}
    script = _parse_script_json(script_json, source=f"bot '{bot_name}' / campaign '{campaign_name}'")
    return script, bot_name


def list_campaigns() -> list[dict[str, str]]:
    """Return [{id, name}] for CLI helper scripts."""
    base, key = _supabase_config()
    url = f"{base}/rest/v1/campaigns"
    params = {"select": "id,name", "order": "name.asc"}

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params, headers=_headers(key))
        resp.raise_for_status()
        return resp.json()


def list_bots() -> list[dict[str, Any]]:
    base, key = _supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {"select": "id,name,campaign_id,campaigns(name)", "order": "name.asc"}

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params, headers=_headers(key))
        resp.raise_for_status()
        return resp.json()


def resolve_script(
    *,
    campaign_id: str | None = None,
    bot_id: str | None = None,
) -> tuple[ScriptConfig, str]:
    """Load script from Supabase or fall back to local defaults."""
    if bot_id:
        return load_script_for_bot(bot_id)
    if campaign_id:
        return load_script_for_campaign(campaign_id), "MIC-TEST"
    return ScriptConfig.load(), "MIC-TEST"
