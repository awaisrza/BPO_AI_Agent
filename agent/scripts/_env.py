"""Load API keys from .env.local, .env, or .env.example."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_ROOT.parent


def env_files() -> list[Path]:
    """Search order: later files override earlier ones."""
    return [
        AGENT_ROOT / ".env.example",
        REPO_ROOT / ".env.local",
        REPO_ROOT / "dashboard" / ".env.local",
        AGENT_ROOT / ".env",
        AGENT_ROOT / ".env.local",
    ]


def load_agent_env() -> None:
    """Load secrets from the first matching env files (rightmost wins)."""
    for path in env_files():
        if path.exists():
            load_dotenv(path, override=True)


def require(key: str) -> str:
    load_agent_env()
    value = os.getenv(key, "").strip()
    if not value:
        paths = "\n  ".join(str(p) for p in env_files())
        raise SystemExit(
            f"ERROR: {key} is missing.\n"
            f"Add it to agent/.env.local or dashboard/.env.local:\n  {paths}"
        )
    return value


def optional(key: str, default: str = "") -> str:
    load_agent_env()
    return os.getenv(key, default).strip() or default
