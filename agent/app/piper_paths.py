"""Shared Piper binary/model resolution and synthesis helpers."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent


def resolve_piper_exe(explicit: str | None = None) -> Path:
    raw = (explicit or os.getenv("PIPER_EXE", "")).strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.extend(
        [
            _AGENT_ROOT / "piper" / "piper.exe",
            _AGENT_ROOT / "piper" / "piper" / "piper.exe",
            _AGENT_ROOT / "piper" / "piper",
            Path("/usr/local/bin/piper"),
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

    checked = "\n".join(f"  {p}" for p in candidates)
    raise FileNotFoundError(
        "piper binary not found. Run scripts/setup_piper.ps1 or set PIPER_EXE.\n"
        f"Checked:\n{checked}"
    )


def resolve_piper_model(explicit: str | None = None) -> Path:
    raw = (explicit or os.getenv("PIPER_MODEL", "")).strip()
    if raw:
        path = Path(raw)
    else:
        path = _AGENT_ROOT / "models" / "en_US-libritts-high.onnx"

    fallbacks = [
        path,
        _AGENT_ROOT / "models" / "en_US-libritts-high.onnx",
        Path(r"C:\piper\models\en_US-libritts-high.onnx"),
    ]
    for candidate in fallbacks:
        if candidate.is_file():
            json_path = candidate.with_suffix(candidate.suffix + ".json")
            if not json_path.is_file():
                raise FileNotFoundError(f"Missing Piper model config: {json_path}")
            return candidate

    checked = "\n".join(f"  {p}" for p in fallbacks)
    raise FileNotFoundError(
        "Piper model not found. Download en_US-libritts-high.onnx (+ .json) and set PIPER_MODEL.\n"
        f"Checked:\n{checked}"
    )


def piper_model_sample_rate(model_path: Path) -> int:
    json_path = model_path.with_suffix(model_path.suffix + ".json")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return int(data.get("audio", {}).get("sample_rate", 22050))


def synthesize_pcm_sync(
    *,
    piper_exe: Path,
    model_path: Path,
    text: str,
    speaker: int | None = None,
) -> bytes:
    """Run Piper with --output_raw; returns 16-bit mono PCM at the model sample rate."""
    cmd = [
        str(piper_exe),
        "--model",
        str(model_path),
        "--output_raw",
    ]
    if speaker is not None:
        cmd.extend(["--speaker", str(speaker)])

    import subprocess

    result = subprocess.run(
        cmd,
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Piper failed: {err}")
    return result.stdout


async def synthesize_pcm_async(
    *,
    piper_exe: Path,
    model_path: Path,
    text: str,
    speaker: int | None = None,
) -> bytes:
    cmd = [
        str(piper_exe),
        "--model",
        str(model_path),
        "--output_raw",
    ]
    if speaker is not None:
        cmd.extend(["--speaker", str(speaker)])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=text.encode("utf-8"))
    if proc.returncode != 0:
        err = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Piper failed: {err}")
    return stdout
