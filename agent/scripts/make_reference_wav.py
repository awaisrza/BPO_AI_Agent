"""Convert greeting.mp3 (or any audio) to Chatterbox reference WAV.

Works on Windows without ffmpeg in PATH (uses bundled ffmpeg via imageio-ffmpeg).

Usage:
  python scripts/make_reference_wav.py
  python scripts/make_reference_wav.py --input my-voice.mp3 --output models/sarah-reference.wav
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _env import AGENT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Chatterbox reference WAV")
    parser.add_argument("--input", default=str(AGENT_ROOT / "greeting.mp3"))
    parser.add_argument("--output", default=str(AGENT_ROOT / "models" / "sarah-reference.wav"))
    parser.add_argument("--seconds", type=float, default=15.0, help="Max length (default 15s)")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.is_file():
        raise SystemExit(
            f"Input not found: {src}\n"
            "Generate Fish audio first:\n"
            "  python scripts/test_fish.py --text \"Hi, this is Sarah on a recorded line.\""
        )

    try:
        import imageio_ffmpeg
    except ImportError:
        raise SystemExit("Run: python -m pip install imageio-ffmpeg") from None

    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-ar",
        "24000",
        "-ac",
        "1",
        "-t",
        str(args.seconds),
        str(dst),
    ]
    subprocess.run(cmd, check=True)
    print(f"Created: {dst}")
    print(f"Size:  {dst.stat().st_size:,} bytes")
    print(f"\nPlay: start {dst}")


if __name__ == "__main__":
    main()
