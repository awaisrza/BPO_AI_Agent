"""Append high-signal call events to /tmp/vicidial_events.log (GPU diagnostics)."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

_TRACE = Path("/tmp/vicidial_events.log")


def trace_call(msg: str) -> None:
    line = msg.rstrip()
    try:
        with _TRACE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        pass
    logger.info(line)
