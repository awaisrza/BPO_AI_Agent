"""Test Piper TTS locally with your own script lines.

Requires piper.exe plus a voice model (.onnx + .onnx.json in the same folder).

Setup (once):
  1. Download https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip
  2. Extract to C:\\piper\\ (you should have C:\\piper\\piper.exe)
  3. Download model files to C:\\piper\\models\\ (see agent/README.md)
  4. Set in agent/.env.local:
       PIPER_EXE=C:\\piper\\piper.exe
       PIPER_MODEL=C:\\piper\\models\\en_US-libritts-high.onnx

Usage:
  python scripts/test_piper.py --text "Hi, this is Sarah on a recorded line."
  python scripts/test_piper.py --text "..." --speaker 1 --output greeting.wav
  python scripts/test_piper.py --script-file my-script.json --all
  python scripts/test_piper.py --campaign-id YOUR-UUID --all
  python scripts/test_piper.py --bot-id YOUR-BOT-UUID --all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _env import AGENT_ROOT, optional

DEFAULT_TEXT = (
    "Hi, this is Sarah. I'm calling about your Medicare benefits — "
    "do you have a quick moment?"
)


def _resolve_piper_exe() -> Path:
    raw = optional("PIPER_EXE")
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.extend(
        [
            AGENT_ROOT / "piper" / "piper.exe",
            AGENT_ROOT / "piper" / "piper" / "piper.exe",
            Path(r"C:\piper\piper.exe"),
        ]
    )

    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path

    configured = Path(raw) if raw else None
    lines = [
        "ERROR: piper.exe not found.",
        "",
        "Install Piper once, then point PIPER_EXE at piper.exe in agent/.env.local:",
        "  https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip",
        "",
        "Suggested extract path (inside this repo):",
        f"  {AGENT_ROOT / 'piper'}",
        "",
        "Checked:",
    ]
    for path in candidates:
        suffix = "  <- configured in PIPER_EXE" if configured and path.resolve() == configured.resolve() else ""
        lines.append(f"  {path}{suffix}")

    if configured and not configured.is_file():
        lines.extend(
            [
                "",
                f"PIPER_EXE is set to {configured}, but that file does not exist.",
                "Either extract Piper there, or update PIPER_EXE to the real path.",
            ]
        )

    raise SystemExit("\n".join(lines))


def _resolve_model_path() -> Path:
    raw = optional("PIPER_MODEL")
    if raw:
        path = Path(raw)
    else:
        path = AGENT_ROOT / "models" / "en_US-libritts-high.onnx"

    if path.is_file():
        json_path = path.with_suffix(path.suffix + ".json")
        if not json_path.is_file():
            raise SystemExit(f"ERROR: Missing model config: {json_path}")
        return path

    fallbacks = [
        path,
        AGENT_ROOT / "models" / "en_US-libritts-high.onnx",
        Path(r"C:\piper\models\en_US-libritts-high.onnx"),
    ]
    checked = "\n".join(f"  {p}" for p in fallbacks)

    raise SystemExit(
        f"ERROR: Piper model not found.\n\n"
        f"Download both files into the same folder:\n"
        f"  en_US-libritts-high.onnx\n"
        f"  en_US-libritts-high.onnx.json\n"
        f"  https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/libritts/high\n\n"
        f"Then set PIPER_MODEL in agent/.env.local, for example:\n"
        f"  PIPER_MODEL={AGENT_ROOT / 'models' / 'en_US-libritts-high.onnx'}\n\n"
        f"Checked:\n{checked}"
    )


def _load_script(args: argparse.Namespace):
    sys.path.insert(0, str(AGENT_ROOT))
    from app.config import ScriptConfig

    if args.script_file:
        path = Path(args.script_file)
        if not path.is_file():
            raise SystemExit(f"ERROR: script file not found: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "greeting" in raw:
            return ScriptConfig.from_script_json(raw)
        return ScriptConfig(**raw)

    if args.campaign_id or args.bot_id:
        from app.supabase_scripts import ScriptLoadError, resolve_script

        try:
            script, _label = resolve_script(
                campaign_id=args.campaign_id,
                bot_id=args.bot_id,
            )
        except ScriptLoadError as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        return script

    return None


def _script_lines(script) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("greeting", script.greeting)]
    if script.pitch:
        lines.append(("pitch", script.pitch))
    for i, question in enumerate(script.qualifying_questions, start=1):
        lines.append((f"qualifying_{i}", question))
    if script.transfer_line:
        lines.append(("transfer", script.transfer_line))
    if script.not_interested_line:
        lines.append(("not_interested", script.not_interested_line))
    return [(label, text.strip()) for label, text in lines if text.strip()]


def _synthesize(
    *,
    piper_exe: Path,
    model_path: Path,
    text: str,
    output_path: Path,
    speaker: int | None,
) -> None:
    cmd = [
        str(piper_exe),
        "--model",
        str(model_path),
        "--output_file",
        str(output_path),
    ]
    if speaker is not None:
        cmd.extend(["--speaker", str(speaker)])

    result = subprocess.run(
        cmd,
        input=text,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"Piper failed:\n{err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Piper TTS with your script")
    parser.add_argument("--text", help="Single line to speak")
    parser.add_argument(
        "--script-file",
        help="JSON script (dashboard script_json shape or ScriptConfig fields)",
    )
    parser.add_argument("--campaign-id", help="Load script from Supabase campaign UUID")
    parser.add_argument("--bot-id", help="Load script from Supabase bot UUID")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Speak every script line (greeting, pitch, qualifiers, transfer, hangup)",
    )
    parser.add_argument(
        "--speaker",
        type=int,
        default=int(optional("PIPER_SPEAKER", "0") or "0"),
        help="Multi-speaker voice index (libritts-high: try 0, 1, or 9)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output WAV path for --text (default: agent/piper-out/line.wav)",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output folder for --all (default: agent/piper-out/)",
    )
    args = parser.parse_args()

    if args.all and not (args.script_file or args.campaign_id or args.bot_id):
        raise SystemExit("ERROR: --all requires --script-file, --campaign-id, or --bot-id")

    if not args.text and not args.all:
        args.text = DEFAULT_TEXT

    piper_exe = _resolve_piper_exe()
    model_path = _resolve_model_path()
    default_dir = AGENT_ROOT / "piper-out"
    default_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        script = _load_script(args)
        assert script is not None
        out_dir = Path(args.out_dir) if args.out_dir else default_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Piper: {piper_exe}")
        print(f"Model: {model_path}")
        print(f"Speaker: {args.speaker}")
        print(f"Output: {out_dir}\n")

        for label, text in _script_lines(script):
            out_path = out_dir / f"{label}.wav"
            print(f"[{label}] {text[:72]}{'...' if len(text) > 72 else ''}")
            _synthesize(
                piper_exe=piper_exe,
                model_path=model_path,
                text=text,
                output_path=out_path,
                speaker=args.speaker,
            )
            print(f"  -> {out_path}")

        print("\n--- PIPER OK ---")
        print(f"Saved {len(_script_lines(script))} file(s) in {out_dir}")
        print(f"\nPlay greeting:\n  start {out_dir / 'greeting.wav'}")
        return

    text = args.text or DEFAULT_TEXT
    out_path = Path(args.output) if args.output else default_dir / "line.wav"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Piper: {piper_exe}")
    print(f"Model: {model_path}")
    print(f"Speaker: {args.speaker}")
    print(f"Text: {text}\n")

    _synthesize(
        piper_exe=piper_exe,
        model_path=model_path,
        text=text,
        output_path=out_path,
        speaker=args.speaker,
    )

    print("\n--- PIPER OK ---")
    print(f"Saved: {out_path}")
    print(f"Size:  {out_path.stat().st_size:,} bytes")
    print("\nPlay it:")
    print(f"  start {out_path}")


if __name__ == "__main__":
    main()
