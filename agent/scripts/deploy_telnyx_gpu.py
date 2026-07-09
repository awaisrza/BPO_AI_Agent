#!/usr/bin/env python3
"""One-shot deploy of Telnyx files onto a GPU instance (when not yet on GitHub)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES: dict[str, str] = {}


def _write(relpath: str, content: str) -> None:
    path = ROOT / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    from importlib import resources

    # Load bundled copies next to this script if present; else use inline fallbacks.
    bundle = Path(__file__).resolve().parent / "telnyx_bundle"
    if bundle.is_dir():
        for name in ("telnyx_server.py", "telnyx_session.py", "run_telnyx.py"):
            src = bundle / name
            if not src.exists():
                raise SystemExit(f"Missing bundle file: {src}")
            dest = (
                f"app/{name}"
                if name != "run_telnyx.py"
                else "run_telnyx.py"
            )
            _write(dest, src.read_text(encoding="utf-8"))
    else:
        raise SystemExit(
            "Run from repo checkout with scripts/telnyx_bundle/, or use git pull after push."
        )

    print("\nVerify:")
    print("  python -c \"from app.telnyx_server import run_telnyx_server; print('telnyx OK')\"")


if __name__ == "__main__":
    main()
