"""Test Chatterbox Turbo TTS with a reference clip and optional campaign script.

Requires CUDA GPU (RunPod or local NVIDIA). First run downloads model weights (~1 GB).

Setup:
  1. Put a 10–20 s WAV reference at agent/models/sarah-reference.wav
     (US female fronter tone, clean audio, no background music)
  2. pip install -r requirements-gpu.txt
  3. Set in .env.local:
       VOICE_BACKEND=chatterbox
       CHATTERBOX_REFERENCE_AUDIO=agent/models/sarah-reference.wav
       WHISPER_DEVICE=cuda
       CHATTERBOX_DEVICE=cuda

Usage:
  python scripts/test_chatterbox.py --text "Hi, this is Sarah on a recorded line."
  python scripts/test_chatterbox.py --campaign-id YOUR-UUID --all
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

from _env import AGENT_ROOT, optional

DEFAULT_TEXT = (
    "Hi, this is Sarah on a recorded line. "
    "I'm calling about your Medicare benefits — do you have a quick moment?"
)


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def _load_script(args: argparse.Namespace):
    sys.path.insert(0, str(AGENT_ROOT))
    from app.config import ScriptConfig

    if args.campaign_id:
        from app.supabase_scripts import resolve_script

        script, _ = resolve_script(campaign_id=args.campaign_id)
        return script
    if args.script_file:
        import json

        raw = json.loads(Path(args.script_file).read_text(encoding="utf-8"))
        if "greeting" in raw:
            return ScriptConfig.from_script_json(raw)
        return ScriptConfig(**raw)
    return None


def _script_lines(script) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    if script.greeting:
        lines.append(("greeting", script.greeting))
    if script.pitch:
        lines.append(("pitch", script.pitch))
    for i, q in enumerate(script.qualifying_questions, start=1):
        lines.append((f"qualifying_{i}", q))
    if script.transfer_line:
        lines.append(("transfer", script.transfer_line))
    if script.not_interested_line:
        lines.append(("not_interested", script.not_interested_line))
    return [(label, text.strip()) for label, text in lines if text.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Chatterbox Turbo TTS")
    parser.add_argument("--text", help="Single line to speak")
    parser.add_argument("--script-file", help="JSON script file")
    parser.add_argument("--campaign-id", help="Load script from Supabase campaign UUID")
    parser.add_argument("--all", action="store_true", help="Speak all script lines")
    parser.add_argument("--out-dir", default="", help="Output folder (default: agent/chatterbox-out/)")
    args = parser.parse_args()

    if args.all and not (args.script_file or args.campaign_id):
        raise SystemExit("ERROR: --all requires --script-file or --campaign-id")

    sys.path.insert(0, str(AGENT_ROOT))
    from app.chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
    from app.chatterbox_tts import synthesize_pcm_sync
    from app.speech_renderer import render_speech, silence_pcm

    reference = resolve_chatterbox_reference(optional("CHATTERBOX_REFERENCE_AUDIO") or None)
    device = resolve_chatterbox_device(optional("CHATTERBOX_DEVICE") or None)
    exaggeration = float(optional("CHATTERBOX_EXAGGERATION", "0.35") or "0.35")
    cfg_weight = float(optional("CHATTERBOX_CFG_WEIGHT", "0.5") or "0.5")
    sample_rate = 16000
    out_dir = Path(args.out_dir) if args.out_dir else AGENT_ROOT / "chatterbox-out"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Device:    {device}")
    print(f"Reference: {reference}")
    print(f"Output:    {out_dir}\n")

    if args.all:
        script = _load_script(args)
        assert script is not None
        for label, text in _script_lines(script):
            out_path = out_dir / f"{label}.wav"
            print(f"[{label}] {text[:72]}{'...' if len(text) > 72 else ''}")
            pcm = synthesize_pcm_sync(
                text=text,
                reference_path=reference,
                device=device,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                sample_rate=sample_rate,
            )
            _write_wav(out_path, pcm, sample_rate)
            print(f"  -> {out_path}")
        print(f"\n--- CHATTERBOX OK --- ({len(_script_lines(script))} files)")
        return

    text = args.text or DEFAULT_TEXT
    out_path = out_dir / "line.wav"
    print(f"Text: {text}\n")
    chunks = render_speech(text)
    pcm_parts: list[bytes] = []
    for chunk in chunks:
        print(f"  chunk: {chunk.text!r} (+{chunk.pause_after_ms}ms)")
        pcm_parts.append(
            synthesize_pcm_sync(
                text=chunk.text,
                reference_path=reference,
                device=device,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                sample_rate=sample_rate,
            )
        )
        if chunk.pause_after_ms > 0:
            pcm_parts.append(silence_pcm(chunk.pause_after_ms, sample_rate))
    pcm = b"".join(pcm_parts)
    _write_wav(out_path, pcm, sample_rate)
    print("--- CHATTERBOX OK ---")
    print(f"Saved: {out_path}")
    print(f"Play:  start {out_path}")


if __name__ == "__main__":
    main()
