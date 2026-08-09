#!/usr/bin/env python3
"""Open caller turn after direct bulk greeting (finish_bot_playback)."""
from __future__ import annotations

from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app" / "vicidial_session.py"
text = p.read_text(encoding="utf-8")

old_claim = """            # Claim before send so StartFrame cannot race a second TTSSpeakFrame.
            if mark_opened:
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.state = CallState.LISTENING"""

new_claim = """            # Claim before send so StartFrame cannot race a second TTSSpeakFrame.
            if mark_opened:
                fronter._opened = True
                fronter._touch_activity()
                fronter._call.begin_bot_reply(1)"""

old_tail = """            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

new_tail = """            duration_ms = await send_direct_bulk_pcm(
                _ws_send_json,
                pcm,
                sample_rate=TELEPHONY_PIPELINE_RATE,
                encoding=bulk_encoding,
            )
            if mark_opened:
                fronter._call.finish_bot_playback()
                await fronter._start_telephony_keepalive()
            _event(f"=== {label} sent direct bulk media (~{duration_ms}ms) ===")
            return True"""

if old_claim not in text:
    raise SystemExit("claim block not found")
text = text.replace(old_claim, new_claim, 1)

if old_tail not in text:
    raise SystemExit("send tail not found")
text = text.replace(old_tail, new_tail, 1)

text = text.replace("            from .speech_renderer import CallState\n\n", "", 1)

p.write_text(text, encoding="utf-8")
print(f"Patched {p}")
