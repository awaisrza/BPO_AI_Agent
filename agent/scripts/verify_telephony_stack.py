#!/usr/bin/env python3
"""Quick check that telephony STT/VAD patches are loaded (run on GPU before dialing)."""

from __future__ import annotations

import inspect
import sys


def main() -> int:
    ok = True

    try:
        from app.pipeline import _build_stt, _telephony_vad_params

        src = inspect.getsource(_build_stt)
        if "no_speech_prob = 0.65 if telephony" not in src:
            print("FAIL: pipeline._build_stt missing telephony Whisper settings")
            ok = False
        else:
            print("OK: telephony Whisper no_speech_prob patch present")

        params = _telephony_vad_params()
        if params.min_volume > 0.4:
            print(f"FAIL: telephony VAD min_volume too high ({params.min_volume})")
            ok = False
        else:
            print(f"OK: telephony VAD min_volume={params.min_volume} stop_secs={params.stop_secs}")
    except ImportError as exc:
        print(f"FAIL: could not import app.pipeline: {exc}")
        return 1

    try:
        from app.conversation import heuristic_classifier, Intent

        if heuristic_classifier("I'm fine") != Intent.POSITIVE:
            print("FAIL: 'I'm fine' not classified as POSITIVE")
            ok = False
        else:
            print("OK: conversation heuristic includes 'I'm fine'")
    except ImportError as exc:
        print(f"FAIL: could not import app.conversation: {exc}")
        return 1

    if ok:
        print("\nTelephony stack looks patched. Pre-warm log should show:")
        print("  STT: faster-whisper (... telephony=True, no_speech_prob=0.65)")
        return 0
    print("\nPull latest code or re-apply patches before dialing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
