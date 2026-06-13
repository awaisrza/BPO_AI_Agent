"""Check Fish Audio API wallet balance (separate from platform credits).

Usage:
  python scripts/test_fish_balance.py
"""

from __future__ import annotations

import sys

from _env import require


def main() -> None:
    api_key = require("FISH_AUDIO_API_KEY")

    try:
        from fishaudio import FishAudio
    except ImportError:
        print("Installing fish-audio-sdk...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "fish-audio-sdk", "-q"])
        from fishaudio import FishAudio

    client = FishAudio(api_key=api_key)
    credits = client.account.get_credits(check_free_credit=True)
    balance = float(credits.credit)

    print("\n--- FISH API WALLET ---")
    print(f"API credit balance: ${balance:.2f}")
    print(f"Free API credit:    {getattr(credits, 'has_free_credit', False)}")

    if balance <= 0:
        print("\nYour 8K platform credits do NOT count here.")
        print("Fish keeps two wallets:")
        print("  1. Platform credits  - using voices on fish.audio website")
        print("  2. API credits       - programmatic TTS (what this bot uses)")
        print("\nFix:")
        print("  1. Open https://fish.audio/app/developers")
        print("  2. Check 'API credit' (not platform credit)")
        print("  3. Add funds (even $5 is enough for testing)")
        print("  4. Re-run: python scripts/test_fish.py")
        sys.exit(1)

    print("\nAPI wallet funded. Run: python scripts/test_fish.py")


if __name__ == "__main__":
    main()
