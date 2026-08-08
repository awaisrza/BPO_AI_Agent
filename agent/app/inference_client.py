"""HTTP client for the shared GPU inference pool (Phase 3)."""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import httpx
from loguru import logger

_DEFAULT_POOL_URL = "http://127.0.0.1:8780"
_DEFAULT_TIMEOUT = float(os.getenv("INFERENCE_POOL_TIMEOUT_SEC", "120") or "120")


def inference_pool_url() -> str | None:
    return os.getenv("INFERENCE_POOL_URL", "").strip() or None


def inference_pool_enabled() -> bool:
    return inference_pool_url() is not None


@lru_cache(maxsize=1)
def get_inference_client() -> "InferenceClient":
    url = inference_pool_url()
    if not url:
        raise RuntimeError("INFERENCE_POOL_URL is not set")
    return InferenceClient(url)


class InferenceClient:
    """Thin sync/async wrapper around inference pool REST endpoints."""

    def __init__(self, base_url: str, *, timeout_sec: float = _DEFAULT_TIMEOUT) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_sec

    def health_sync(self) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self._base}/health")
            resp.raise_for_status()
            return resp.json()

    def wait_until_ready(
        self,
        *,
        timeout_sec: float = 180.0,
        poll_sec: float = 2.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        last_error: str | None = None
        while time.monotonic() < deadline:
            try:
                body = self.health_sync()
                if body.get("ok"):
                    logger.info(
                        f"Inference pool ready at {self._base} "
                        f"(cache={body.get('cache_size', 0)} lines)"
                    )
                    return body
                last_error = str(body.get("error") or "pool not ready")
            except Exception as exc:
                last_error = str(exc)
            time.sleep(poll_sec)
        raise TimeoutError(
            f"Inference pool at {self._base} not ready after {timeout_sec:.0f}s: {last_error}"
        )

    def warm_cache_sync(
        self,
        texts: list[str],
        *,
        sample_rate: int,
        telephony: bool,
    ) -> dict[str, Any]:
        payload = {
            "texts": texts,
            "sample_rate": sample_rate,
            "telephony": telephony,
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base}/v1/cache/warm", json=payload)
            resp.raise_for_status()
            return resp.json()

    def synthesize_sync(
        self,
        text: str,
        *,
        sample_rate: int,
        telephony: bool,
    ) -> bytes:
        payload = {
            "text": text,
            "sample_rate": sample_rate,
            "telephony": telephony,
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base}/v1/tts", json=payload)
            resp.raise_for_status()
            return resp.content

    def transcribe_sync(self, wav_bytes: bytes, *, no_speech_prob: float) -> str:
        params = {"no_speech_prob": str(no_speech_prob)}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base}/v1/stt",
                content=wav_bytes,
                headers={"Content-Type": "application/octet-stream"},
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()
            return str(body.get("text") or "").strip()

    async def synthesize(
        self,
        text: str,
        *,
        sample_rate: int,
        telephony: bool,
    ) -> bytes:
        payload = {
            "text": text,
            "sample_rate": sample_rate,
            "telephony": telephony,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base}/v1/tts", json=payload)
            resp.raise_for_status()
            return resp.content

    async def transcribe(self, wav_bytes: bytes, *, no_speech_prob: float) -> str:
        params = {"no_speech_prob": str(no_speech_prob)}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/v1/stt",
                content=wav_bytes,
                headers={"Content-Type": "application/octet-stream"},
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()
            return str(body.get("text") or "").strip()
