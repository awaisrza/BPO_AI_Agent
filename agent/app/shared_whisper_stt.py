"""Whisper STT: shared faster-whisper weights, fresh processor state per call."""

from __future__ import annotations

from typing import Any

from loguru import logger

try:
    from pipecat.services.whisper.stt import WhisperSTTService
except Exception:  # pragma: no cover
    WhisperSTTService = object  # type: ignore

_shared_whisper_models: dict[tuple[Any, ...], object] = {}


class SharedModelWhisperSTTService(WhisperSTTService):
    """One WhisperModel in memory; new SegmentedSTTService state each dial."""

    def _load(self) -> None:
        try:
            from faster_whisper import WhisperModel
            from pipecat.services.settings import assert_given

            model_name = assert_given(self._settings.model)
            if model_name is None:
                raise ValueError("Whisper model must be specified")
            key = (model_name, self._device, self._compute_type)
            model = _shared_whisper_models.get(key)
            if model is None:
                logger.debug(f"Loading shared Whisper model {model_name}...")
                model = WhisperModel(
                    model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )
                _shared_whisper_models[key] = model
                logger.debug("Loaded shared Whisper model")
            self._model = model
        except ModuleNotFoundError as exc:
            logger.error(f"Exception: {exc}")
            logger.error("In order to use Whisper, you need to `pip install pipecat-ai[whisper]`.")
            self._model = None
