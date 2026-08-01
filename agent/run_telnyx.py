#!/usr/bin/env python3
"""Place a Telnyx outbound call and run the fronter pipeline on the media stream."""

from __future__ import annotations

import argparse

from app.supabase_client import ScriptLoadError
from app.supabase_scripts import resolve_script
from app.telnyx_server import run_telnyx_server


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Fronter — Telnyx phone test")
    parser.add_argument(
        "--campaign-id",
        required=True,
        help="Supabase campaign UUID (loads script greeting/pitch/qualifiers)",
    )
    parser.add_argument(
        "--script-file",
        help="Local script JSON (skips Supabase — use when GPU cannot reach Supabase)",
    )
    parser.add_argument(
        "--dial",
        metavar="E164",
        help="Outbound number to dial, e.g. +923142222318",
    )
    parser.add_argument(
        "--agent-user",
        default="TELNYX-TEST",
        help="ViciDial agent label (mic-test mode ignores ViciDial)",
    )
    args = parser.parse_args()

    try:
        ctx = resolve_script(
            campaign_id=args.campaign_id,
            script_file=args.script_file,
        )
    except ScriptLoadError as exc:
        raise SystemExit(str(exc)) from exc

    run_telnyx_server(ctx.script, args.agent_user or ctx.agent_user, dial_to=args.dial)


if __name__ == "__main__":
    main()
