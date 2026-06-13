"""Run all API smoke tests in order: Fish → Gemini → Deepgram.

Usage:
  python scripts/test_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

TESTS = [
    ("Fish Audio TTS", "test_fish.py", []),
    ("Gemini LLM", "test_gemini.py", []),
    ("Deepgram STT", "test_deepgram.py", []),
]


def run(name: str, script: str, extra_args: list[str]) -> bool:
    print("\n" + "=" * 60)
    print(f"  {name}")
    print("=" * 60)
    result = subprocess.run(
        [PYTHON, str(SCRIPTS_DIR / script), *extra_args],
        cwd=SCRIPTS_DIR.parent,
    )
    return result.returncode == 0


def main() -> None:
    passed = 0
    failed: list[str] = []

    for name, script, args in TESTS:
        if run(name, script, args):
            passed += 1
        else:
            failed.append(name)

    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{len(TESTS)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("All API tests passed.")


if __name__ == "__main__":
    main()
