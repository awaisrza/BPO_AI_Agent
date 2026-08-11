#!/usr/bin/env python3
"""Verify GPU + bridge have fixes for post-greeting caller replies."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "vicidial" / "agi_bridge.py"

CHECKS: list[tuple[str, Path, str, str]] = [
    (
        "caller turn after direct greeting",
        ROOT / "app" / "pipeline.py",
        "finish_bot_playback()\n        await self._start_telephony_keepalive()\n        self._move_pending_to_buffer()",
        "git pull && restart supervisor",
    ),
    (
        "greeting completion hook in vicidial session",
        ROOT / "app" / "vicidial_session.py",
        "await fronter.on_direct_greeting_complete()",
        "python scripts/patch_caller_reply_fix.py",
    ),
    (
        "caller audio during greeting wait (bridge)",
        BRIDGE,
        "_try_forward_caller_audio",
        "copy scripts/vicidial/agi_bridge.py to /usr/local/bin/ai-fronter-bridge.py on ViciDial",
    ),
]

NEGATIVE: list[tuple[str, Path, str, str]] = [
    (
        "no 3s runner join hangup",
        ROOT / "app" / "vicidial_session.py",
        "await asyncio.wait_for(runner_task",
        "python scripts/patch_runner_timeout_fix.py",
    ),
]


def main() -> int:
    ok = True
    for label, path, needle, fix in CHECKS:
        if not path.is_file():
            print(f"FAIL  {label}: missing {path}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            print(f"FAIL  {label}: {needle!r} not in {path.name}")
            print(f"      fix: {fix}")
            ok = False
        else:
            print(f"OK    {label}")

    for label, path, bad, fix in NEGATIVE:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if bad in text:
            print(f"FAIL  {label}: found {bad!r} in {path.name}")
            print(f"      fix: {fix}")
            ok = False
        else:
            print(f"OK    {label}")

    if ok:
        print("\nAll call patches present. Restart supervisor + bridge, then test.")
        return 0
    print("\nApply fixes above, restart fleet, redeploy bridge, then place a test call.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
