#!/usr/bin/env python3
"""One-shot check: GPU has all fixes for post-greeting conversation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ("direct reply path", ROOT / "app" / "pipeline.py", "set_direct_telephony_media"),
    ("direct reply send", ROOT / "app" / "pipeline.py", "direct reply sent"),
    ("tts utterance flush", ROOT / "app" / "tts_spoken_chunk.py", "UtteranceFlushFrame"),
    ("stt yield fix", ROOT / "app" / "pooled_stt.py", "yield TranscriptionFrame"),
    ("bulk media trace", ROOT / "app" / "telnyx_media.py", "bulk media sent"),
]


def main() -> int:
    ok = True
    for label, path, needle in REQUIRED:
        if not path.is_file():
            print(f"FAIL  {label}: missing {path.name}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            print(f"FAIL  {label}: {needle!r} not in {path.name}")
            ok = False
        else:
            print(f"OK    {label}")

    print()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_call_patches.py")])
    if r.returncode != 0:
        ok = False

    if ok:
        print("\nAll fixes present. Run: bash scripts/restart_fleet_supervisor.sh")
        print("On test call, vicidial_events.log must show:")
        print("  === direct telephony reply media enabled ===")
        print("  === direct reply sent ===  (after you speak)")
        return 0
    print("\nSync latest code to GPU before testing again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
