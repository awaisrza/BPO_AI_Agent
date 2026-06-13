"""Test Fish Audio TTS (mouth). Saves agent/greeting.mp3 you can play.

Usage:
  python scripts/test_fish.py
  python scripts/test_fish.py --text "Hi, this is Sarah calling on a recorded line."
"""

from __future__ import annotations

import argparse
import sys

import httpx

from _env import AGENT_ROOT, optional, require

DEFAULT_GREETING = (
    "Hi, this is Sarah calling on a recorded line. "
    "How are you doing today?"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Fish Audio TTS")
    parser.add_argument("--text", default=DEFAULT_GREETING, help="Text to speak")
    args = parser.parse_args()

    api_key = require("FISH_AUDIO_API_KEY")
    model = optional("FISH_AUDIO_MODEL", "s1")
    reference_id = optional("FISH_AUDIO_REFERENCE_ID")

    payload: dict = {
        "text": args.text,
        "format": "mp3",
        "latency": "balanced",
    }
    if reference_id:
        payload["reference_id"] = reference_id
    else:
        print("WARNING: FISH_AUDIO_REFERENCE_ID is empty — voice may sound generic.")

    print(f"Sending to Fish Audio (model={model})...")
    resp = httpx.post(
        "https://api.fish.audio/v1/tts",
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": model,
        },
        timeout=90.0,
    )

    print(f"Status: {resp.status_code}")
    if resp.status_code == 402:
        print("Error:", resp.text)
        print("\n--- LIKELY CAUSE ---")
        print("Platform credits (8K/8K on the website) are NOT API credits.")
        print("Check your API wallet:")
        print("  python scripts/test_fish_balance.py")
        print("Add API funds:")
        print("  https://fish.audio/app/developers")
        sys.exit(1)
    if resp.status_code == 400 and "Reference not found" in resp.text:
        print("Error:", resp.text)
        print("\n--- LIKELY CAUSE ---")
        print(f"FISH_AUDIO_REFERENCE_ID is invalid: {reference_id!r}")
        print("List valid voice IDs:")
        print("  python scripts/test_fish_voices.py --pick-first")
        print("\nHow to get a valid id:")
        print("  1. Open a voice on fish.audio")
        print("  2. Copy id from URL: https://fish.audio/m/YOUR_ID_HERE")
        print("  3. Update dashboard/.env.local -> FISH_AUDIO_REFERENCE_ID=...")
        sys.exit(1)
    if resp.status_code != 200:
        print("Error:", resp.text)
        sys.exit(1)

    out = AGENT_ROOT / "greeting.mp3"
    out.write_bytes(resp.content)

    print("\n--- FISH AUDIO OK ---")
    print(f"Saved: {out}")
    print(f"Size:  {len(resp.content):,} bytes")
    print("\nPlay it:")
    print(f"  start {out}")


if __name__ == "__main__":
    main()
