"""Chatterbox reference audio and device resolution."""

from __future__ import annotations

import os
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent


def resolve_chatterbox_device(explicit: str | None = None) -> str:
    raw = (explicit or os.getenv("CHATTERBOX_DEVICE", "") or os.getenv("WHISPER_DEVICE", "auto")).strip()
    if raw and raw != "auto":
        return raw
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def resolve_chatterbox_reference(explicit: str | None = None) -> Path:
    raw = (explicit or os.getenv("CHATTERBOX_REFERENCE_AUDIO", "")).strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.extend(
        [
            _AGENT_ROOT / "models" / "sarah-reference.wav",
            _AGENT_ROOT / "models" / "reference.wav",
            _AGENT_ROOT / "voices" / "sarah-reference.wav",
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
        "Chatterbox reference audio not found (10–20 s WAV for voice clone).\n"
        "Set CHATTERBOX_REFERENCE_AUDIO in .env.local, e.g.:\n"
        f"  CHATTERBOX_REFERENCE_AUDIO={_AGENT_ROOT / 'models' / 'sarah-reference.wav'}\n\n"
        f"Checked:\n{checked}"
    )
