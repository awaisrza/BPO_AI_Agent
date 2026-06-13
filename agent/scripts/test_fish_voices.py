"""List Fish Audio voices and validate FISH_AUDIO_REFERENCE_ID.

Usage:
  python scripts/test_fish_voices.py
  python scripts/test_fish_voices.py --pick-first
"""

from __future__ import annotations

import argparse
import sys

from _env import optional, require


def voice_id(v) -> str:
    return getattr(v, "id", None) or getattr(v, "_id", "") or ""


def voice_title(v) -> str:
    return getattr(v, "title", None) or getattr(v, "name", "?") or "?"


def voice_state(v) -> str:
    return getattr(v, "state", "?") or "?"


def main() -> None:
    parser = argparse.ArgumentParser(description="List Fish voices")
    parser.add_argument(
        "--pick-first",
        action="store_true",
        help="Print the first usable voice id to put in FISH_AUDIO_REFERENCE_ID",
    )
    args = parser.parse_args()

    api_key = require("FISH_AUDIO_API_KEY")
    current_ref = optional("FISH_AUDIO_REFERENCE_ID")

    try:
        from fishaudio import FishAudio
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "fish-audio-sdk", "-q"])
        from fishaudio import FishAudio

    client = FishAudio(api_key=api_key)

    print("\n--- CURRENT REFERENCE_ID ---")
    if current_ref:
        print(current_ref)
        try:
            voice = client.voices.get(current_ref)
            print(f"Status: FOUND - {voice_title(voice)} (state={voice_state(voice)})")
        except Exception as exc:  # noqa: BLE001
            print(f"Status: NOT FOUND - {exc}")
            print("This is why test_fish.py returns 'Reference not found'.")
    else:
        print("(empty)")

    print("\n--- YOUR VOICES ---")
    yours: list = []
    try:
        result = client.voices.list(self_only=True)
        yours = list(getattr(result, "items", None) or [])
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list your voices: {exc}")

    if yours:
        for v in yours[:20]:
            print(f"  {voice_title(v)}")
            print(f"    id:    {voice_id(v)}")
            print(f"    state: {voice_state(v)}")
    else:
        print("  (none - you have not created/cloned any voices yet)")

    print("\n--- PUBLIC ENGLISH VOICES (pick one) ---")
    public: list = []
    try:
        result = client.voices.list(language="en", page_size=10)
        public = list(getattr(result, "items", None) or [])
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list public voices: {exc}")

    for v in public[:10]:
        print(f"  {voice_title(v)} -> {voice_id(v)}")

    pick = None
    if yours:
        pick = voice_id(yours[0])
        print(f"\nSuggested (your voice): {pick}")
    elif public:
        # Prefer a natural US caller name if available (good for fronter bots).
        sarah = next((v for v in public if "sarah" in voice_title(v).lower()), None)
        pick = voice_id(sarah) if sarah else voice_id(public[0])
        label = voice_title(sarah) if sarah else voice_title(public[0])
        print(f"\nSuggested (public voice): {label} -> {pick}")

    if args.pick_first and pick:
        print("\nAdd to dashboard/.env.local:")
        print(f"FISH_AUDIO_REFERENCE_ID={pick}")
    elif not current_ref or (current_ref and yours == [] and public):
        print("\nFix:")
        print("  1. Open https://fish.audio and pick a voice")
        print("  2. Copy id from URL: https://fish.audio/m/YOUR_ID_HERE")
        print("  3. Set FISH_AUDIO_REFERENCE_ID=YOUR_ID_HERE in dashboard/.env.local")
        print("  4. Re-run: python scripts/test_fish.py")


if __name__ == "__main__":
    main()
