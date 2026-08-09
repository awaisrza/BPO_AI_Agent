#!/usr/bin/env python3
"""One-off patch: greeting_pcm_from_cache pool synthesize fallback."""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "app" / "telnyx_media.py"
text = path.read_text(encoding="utf-8")

text = text.replace(
    """    cache = getattr(tts, "_cache", None)
    if not cache:
        return None""",
    """    cache = getattr(tts, "_cache", None)
    if cache is None:
        cache = {}""",
    1,
)

old_loop = """    for chunk in chunks:
        pcm = cache.get(chunk.text.strip())
        if pcm is None:
            return None
        parts.append(pcm)
    return b"".join(parts)"""

new_loop = """    for chunk in chunks:
        line = chunk.text.strip()
        pcm = cache.get(line)
        if pcm is None:
            pcm = _synthesize_greeting_line(line)
            if pcm is not None and isinstance(cache, dict):
                cache[line] = pcm
        if pcm is None:
            return None
        parts.append(pcm)
    return b"".join(parts) if parts else None


def _synthesize_greeting_line(line: str) -> bytes | None:
    if not line.strip():
        return None
    try:
        from .inference_client import inference_pool_enabled, get_inference_client

        if inference_pool_enabled():
            return get_inference_client().synthesize_sync(
                line.strip(),
                sample_rate=TELEPHONY_PIPELINE_RATE,
                telephony=True,
            )
    except Exception as exc:
        logger.warning(f"Greeting pool synthesize failed ({line[:32]!r}): {exc}")
    return None"""

if old_loop not in text:
    raise SystemExit("greeting loop block not found")
text = text.replace(old_loop, new_loop, 1)
path.write_text(text, encoding="utf-8")
print(f"Patched {path}")
