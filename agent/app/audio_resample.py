"""High-quality PCM16 resampling for telephony pipelines."""

from __future__ import annotations

import audioop


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample mono PCM16; prefers torchaudio sinc, falls back to audioop."""
    if not pcm or src_rate == dst_rate:
        return pcm

    try:
        import torch
        import torchaudio.functional as F

        wav = torch.frombuffer(bytearray(pcm), dtype=torch.int16).float().div(32768.0)
        wav = wav.unsqueeze(0)
        resampled = F.resample(
            wav,
            orig_freq=src_rate,
            new_freq=dst_rate,
            lowpass_filter_width=64,
            rolloff=0.9475937167399596,
            resampling_method="sinc_interp_kaiser",
        )
        return (
            resampled.squeeze(0)
            .clamp(-1.0, 1.0)
            .mul(32767.0)
            .to(torch.int16)
            .numpy()
            .tobytes()
        )
    except Exception:
        converted, _ = audioop.ratecv(pcm, 2, 1, src_rate, dst_rate, None)
        return converted


def telephony_preemphasis(pcm: bytes, *, coef: float = 0.95) -> bytes:
    """Boost speech clarity before 8 kHz PCMU (helps consonants on phone lines)."""
    if len(pcm) < 4:
        return pcm
    samples = memoryview(pcm).cast("h")
    out = bytearray(len(pcm))
    out_view = memoryview(out).cast("h")
    out_view[0] = samples[0]
    for i in range(1, len(samples)):
        boosted = int(samples[i] - coef * samples[i - 1])
        if boosted > 32767:
            boosted = 32767
        elif boosted < -32768:
            boosted = -32768
        out_view[i] = boosted
    return bytes(out)


def normalize_pcm16(pcm: bytes, *, target_peak: float = 0.92) -> bytes:
    """Lift quiet TTS output so phone codecs (PCMU) don't sound muffled."""
    if not pcm:
        return pcm
    peak = audioop.max(pcm, 2)
    if peak <= 0:
        return pcm
    max_peak = int(32767 * target_peak)
    if peak >= max_peak:
        return pcm
    factor = max_peak / peak
    return audioop.mul(pcm, 2, factor)


def enhance_for_telephony(pcm: bytes) -> bytes:
    """Level-normalize for PSTN; skip harsh pre-emphasis (sounds thin/robotic)."""
    return normalize_pcm16(pcm, target_peak=0.91)
