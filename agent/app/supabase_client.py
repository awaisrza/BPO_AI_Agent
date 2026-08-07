"""Shared Supabase REST helpers for the agent."""

from __future__ import annotations

from .config import settings


class ScriptLoadError(RuntimeError):
    pass


def supabase_config() -> tuple[str, str]:
    url = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_service_role_key
    if not url or not key:
        raise ScriptLoadError(
            "Supabase not configured for the agent. Add to dashboard/.env.local or agent/.env:\n"
            "  NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co\n"
            "  SUPABASE_SERVICE_ROLE_KEY=your-service-role-key\n"
            "(Project Settings -> API -> service_role - keep secret, never commit)"
        )
    return url, key


def supabase_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
