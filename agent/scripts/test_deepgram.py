"""Test Deepgram STT (ears).

Usage:
  python scripts/test_deepgram.py
  python scripts/test_deepgram.py --audio test.wav
  python scripts/test_deepgram.py --url https://example.com/sample.wav
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from _env import AGENT_ROOT, optional, require

DEFAULT_SAMPLE_URL = (
    "https://static.deepgram.com/examples/Bueller-Life-moves-pretty-fast.wav"
)


def load_audio(path: Path | None, url: str | None) -> tuple[bytes, str]:
    if path:
        if not path.exists():
            raise SystemExit(f"ERROR: Audio file not found: {path}")
        return path.read_bytes(), path.suffix.lstrip(".") or "wav"

    if url:
        print(f"Downloading sample audio: {url}")
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.content, "wav"

    local = AGENT_ROOT / "test.wav"
    if local.exists():
        print(f"Using local recording: {local}")
        return local.read_bytes(), "wav"

    print("No local test.wav - using Deepgram public sample.")
    resp = httpx.get(DEFAULT_SAMPLE_URL, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content, "wav"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Deepgram STT")
    parser.add_argument("--audio", type=Path, help="Path to WAV/MP3 recording")
    parser.add_argument("--url", help="URL to audio file")
    args = parser.parse_args()

    api_key = require("DEEPGRAM_API_KEY")
    audio, fmt = load_audio(args.audio, args.url)

    print("Sending audio to Deepgram (model=nova-3)...")
    resp = httpx.post(
        "https://api.deepgram.com/v1/listen",
        params={
            "model": "nova-3",
            "language": "en-US",
            "punctuate": "true",
            "smart_format": "true",
        },
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": f"audio/{fmt}",
        },
        content=audio,
        timeout=60.0,
    )

    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print("Error:", resp.text)
        sys.exit(1)

    data = resp.json()
    transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    confidence = data["results"]["channels"][0]["alternatives"][0].get("confidence")

    print("\n--- DEEPGRAM OK ---")
    print("TRANSCRIPT:", transcript)
    if confidence is not None:
        print(f"CONFIDENCE: {confidence:.2%}")
    print("\nNext: record yourself saying 'Yes I own my home' as agent/test.wav and re-run.")


if __name__ == "__main__":
    main()
