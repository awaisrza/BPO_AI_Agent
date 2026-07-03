#!/usr/bin/env python3
"""Daily.co voice test — open the printed link on your phone (Pakistan OK, no Twilio).

Usage:
  pip install "pipecat-ai[daily,whisper]" aiohttp
  Set DAILY_API_KEY in agent/.env.local
  python scripts/run_daily_call.py --campaign-id YOUR-UUID
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from _env import AGENT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily.co voice call test")
    parser.add_argument("--campaign-id", required=True, help="Supabase campaign UUID")
    args = parser.parse_args()

    sys.path.insert(0, str(AGENT_ROOT))
    from app.daily_session import run_daily_call
    from app.supabase_scripts import resolve_script

    script, agent_user = resolve_script(campaign_id=args.campaign_id)
    asyncio.run(run_daily_call(script, agent_user))


if __name__ == "__main__":
    main()
