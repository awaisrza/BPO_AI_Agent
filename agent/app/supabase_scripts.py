"""Load campaign scripts from Supabase (dashboard → agent)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from .bot_context import BotRunContext
from .config import ScriptConfig
from .supabase_client import ScriptLoadError, supabase_config, supabase_headers

_AGENT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _AGENT_ROOT / ".cache" / "campaigns"
_BUNDLED_DIR = _AGENT_ROOT / "scripts" / "campaigns"
_HTTP_TIMEOUT = 30.0
_HTTP_RETRIES = 3


def _parse_script_json(data: dict[str, Any], *, source: str) -> ScriptConfig:
    if not data.get("greeting") or not data.get("pitch"):
        raise ScriptLoadError(f"Campaign script at {source} is missing greeting or pitch.")
    script = ScriptConfig.from_script_json(data)
    logger.info(
        f"Loaded script from {source}: "
        f"{len(script.qualifying_questions)} qualifying question(s)"
    )
    return script


def _cache_path(campaign_id: str) -> Path:
    return _CACHE_DIR / f"{campaign_id}.json"


def _write_cache(campaign_id: str, script_json: dict[str, Any]) -> None:
    path = _cache_path(campaign_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(script_json, indent=2), encoding="utf-8")
    logger.debug(f"Cached campaign script to {path}")


def _load_cached_campaign(campaign_id: str) -> ScriptConfig | None:
    path = _cache_path(campaign_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _parse_script_json(raw, source=f"cache {path.name}")


def _load_bundled_campaign(campaign_id: str) -> ScriptConfig | None:
    path = _BUNDLED_DIR / f"{campaign_id}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _parse_script_json(raw, source=f"bundled {path.name}")


def _fetch_campaign_row(campaign_id: str) -> dict[str, Any]:
    base, key = supabase_config()
    url = f"{base}/rest/v1/campaigns"
    params = {"id": f"eq.{campaign_id}", "select": "id,name,script_json"}

    last_error: Exception | None = None
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        for attempt in range(1, _HTTP_RETRIES + 1):
            try:
                resp = client.get(url, params=params, headers=supabase_headers(key))
                resp.raise_for_status()
                rows = resp.json()
                if not rows:
                    raise ScriptLoadError(f"No campaign found with id={campaign_id}")
                return rows[0]
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_error = exc
                logger.warning(
                    f"Supabase request failed (attempt {attempt}/{_HTTP_RETRIES}): {exc}"
                )
                if attempt < _HTTP_RETRIES:
                    time.sleep(2 * attempt)

    assert last_error is not None
    raise last_error


def load_script_for_campaign(campaign_id: str) -> ScriptConfig:
    """Load script_json for a campaign UUID."""
    try:
        row = _fetch_campaign_row(campaign_id)
    except ScriptLoadError:
        raise
    except Exception as exc:
        cached = _load_cached_campaign(campaign_id)
        if cached is not None:
            logger.warning(f"Supabase unreachable ({exc}) — using cached script")
            return cached
        bundled = _load_bundled_campaign(campaign_id)
        if bundled is not None:
            logger.warning(f"Supabase unreachable ({exc}) — using bundled script")
            return bundled
        raise ScriptLoadError(
            f"Cannot reach Supabase ({exc}) and no local script for campaign {campaign_id}.\n"
            "Options:\n"
            "  1. Retry when the GPU has outbound HTTPS to Supabase\n"
            f"  2. python run_telnyx.py --script-file scripts/campaigns/{campaign_id}.json ...\n"
            "  3. Fetch once online to populate .cache/campaigns/"
        ) from exc

    name = row.get("name") or campaign_id
    script_json = row.get("script_json") or {}
    if script_json:
        _write_cache(campaign_id, script_json)
    return _parse_script_json(script_json, source=f"Supabase campaign '{name}'")


def load_bot_context(bot_id: str) -> BotRunContext:
    """Load script + ViciDial agent mapping for a dashboard bot."""
    from .vicidial_config import resolve_vicidial_config

    base, key = supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {
        "id": f"eq.{bot_id}",
        "select": "id,name,org_id,vicidial_agent_user,campaign_id,campaigns(script_json,name,vicidial_campaign_id)",
    }

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        raise ScriptLoadError(f"No bot found with id={bot_id}")

    bot = rows[0]
    bot_name = bot.get("name") or bot_id
    agent_user = (bot.get("vicidial_agent_user") or "").strip() or bot_name
    org_id = bot.get("org_id")
    campaign = bot.get("campaigns")
    if not campaign:
        raise ScriptLoadError(
            f"Bot '{bot_name}' has no campaign assigned. Assign it in Dashboard → Bots."
        )

    campaign_name = campaign.get("name") or bot.get("campaign_id")
    script_json = campaign.get("script_json") or {}
    script = _parse_script_json(
        script_json, source=f"bot '{bot_name}' / campaign '{campaign_name}'"
    )
    vicidial_campaign_id = (campaign.get("vicidial_campaign_id") or "").strip() or None
    vicidial = resolve_vicidial_config(org_id)

    if not vicidial:
        logger.warning(
            f"Bot '{bot_name}': no ViciDial creds in Supabase org or agent .env — transfers will fail."
        )

    return BotRunContext(
        script=script,
        bot_id=bot_id,
        bot_name=bot_name,
        agent_user=agent_user,
        vicidial_campaign_id=vicidial_campaign_id,
        org_id=org_id,
        vicidial=vicidial,
    )


def load_script_for_bot(bot_id: str) -> tuple[ScriptConfig, str]:
    """Load script via bot → assigned campaign. Returns (script, vicidial_agent_user)."""
    ctx = load_bot_context(bot_id)
    return ctx.script, ctx.agent_user


def load_campaign_context(campaign_id: str) -> BotRunContext:
    """Load campaign script + org ViciDial settings (manual / test runs)."""
    from .vicidial_config import resolve_vicidial_config

    base, key = supabase_config()
    url = f"{base}/rest/v1/campaigns"
    params = {
        "id": f"eq.{campaign_id}",
        "select": "id,name,org_id,vicidial_campaign_id,script_json",
    }

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        rows = resp.json()

    if not rows:
        raise ScriptLoadError(f"No campaign found with id={campaign_id}")

    row = rows[0]
    name = row.get("name") or campaign_id
    script_json = row.get("script_json") or {}
    script = _parse_script_json(script_json, source=f"Supabase campaign '{name}'")
    org_id = row.get("org_id")
    vicidial = resolve_vicidial_config(org_id)

    return BotRunContext(
        script=script,
        bot_id=None,
        bot_name=name,
        agent_user="MIC-TEST",
        vicidial_campaign_id=(row.get("vicidial_campaign_id") or "").strip() or None,
        org_id=org_id,
        vicidial=vicidial,
    )


def list_campaigns() -> list[dict[str, str]]:
    """Return [{id, name}] for CLI helper scripts."""
    base, key = supabase_config()
    url = f"{base}/rest/v1/campaigns"
    params = {"select": "id,name", "order": "name.asc"}

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        return resp.json()


def list_bots() -> list[dict[str, Any]]:
    base, key = supabase_config()
    url = f"{base}/rest/v1/bots"
    params = {"select": "id,name,campaign_id,campaigns(name)", "order": "name.asc"}

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=supabase_headers(key))
        resp.raise_for_status()
        return resp.json()


def resolve_script(
    *,
    campaign_id: str | None = None,
    bot_id: str | None = None,
    script_file: str | None = None,
) -> tuple[ScriptConfig, str]:
    """Load script from file, Supabase, or bundled/cached fallback."""
    if script_file:
        path = Path(script_file)
        if not path.exists():
            raise ScriptLoadError(f"Script file not found: {script_file}")
        return ScriptConfig.load(str(path)), "MIC-TEST"
    if bot_id:
        return load_script_for_bot(bot_id)
    if campaign_id:
        return load_script_for_campaign(campaign_id), "MIC-TEST"
    return ScriptConfig.load(), "MIC-TEST"
