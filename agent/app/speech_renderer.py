"""Convert written bot text into short spoken chunks for natural TTS pacing.

All FSM, knowledge-base, and Gemini replies should pass through ``render_speech``
(via ``SpeechRendererNode`` in the live pipeline) before synthesis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from loguru import logger

try:
    from pipecat.frames.frames import (
        BotStoppedSpeakingFrame,
        DataFrame,
        Frame,
        InterruptionFrame,
        TTSSpeakFrame,
        UserStartedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover
    PIPECAT_AVAILABLE = False
    DataFrame = object  # type: ignore
    FrameProcessor = object  # type: ignore
    FrameDirection = object  # type: ignore


# --- Spoken text normalization -------------------------------------------------

_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bI am calling to verify your Medicare eligibility\b", re.I), "I'm calling about your Medicare plan"),
    (re.compile(r"\bassist you in understanding\b", re.I), "help you understand"),
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bWould you be able to\b", re.I), "Can you"),
    (re.compile(r"\bDo you have a moment to speak\b", re.I), "Do you have a quick moment"),
    (re.compile(r"\bI am calling regarding\b", re.I), "I'm calling about"),
    (re.compile(r"\bI am reaching out\b", re.I), "I'm calling"),
    (re.compile(r"\bper our records\b", re.I), "from what we have"),
    (re.compile(r"\bat this time\b", re.I), "right now"),
    (re.compile(r"\bfor your information\b", re.I), "just so you know"),
    (re.compile(r"\bPlease be advised\b", re.I), "Just so you know"),
    (re.compile(r"\bI understand your concern\b", re.I), "I hear you"),
    (re.compile(r"\bI completely understand\b", re.I), "I get it"),
    (re.compile(r"\bNo problem at all\b", re.I), "No problem"),
    (re.compile(r"\bI am\b", re.I), "I'm"),
    (re.compile(r"\bWe are\b", re.I), "We're"),
    (re.compile(r"\bYou are\b", re.I), "You're"),
    (re.compile(r"\bIt is\b", re.I), "It's"),
    (re.compile(r"\bThat is\b", re.I), "That's"),
    (re.compile(r"\bCannot\b", re.I), "Can't"),
    (re.compile(r"\bDo not\b", re.I), "Don't"),
    (re.compile(r"\bThank you for your time\b", re.I), "Thanks for your time"),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT = re.compile(r"\s*[,;]\s*")


@dataclass(frozen=True)
class SpeechChunk:
    text: str
    pause_after_ms: int = 0


class CallState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class CallController:
    """Shared call-state for barge-in and turn coordination."""

    def __init__(self) -> None:
        self.state = CallState.IDLE
        self.interrupted = False

    def should_interrupt(self) -> bool:
        return self.state == CallState.SPEAKING

    def on_interruption(self) -> None:
        self.interrupted = True
        self.state = CallState.LISTENING
        logger.debug("CallController: interrupted -> listening")

    def on_response_start(self) -> None:
        self.interrupted = False
        self.state = CallState.SPEAKING

    def on_bot_stopped(self) -> None:
        self.interrupted = False
        self.state = CallState.LISTENING

    def on_processing(self) -> None:
        self.state = CallState.PROCESSING

    def on_listening(self) -> None:
        self.interrupted = False
        self.state = CallState.LISTENING


def prepare_for_speech(text: str) -> str:
    """Normalize any bot reply (FSM, KB, Gemini) before chunking/TTS."""
    return normalize_spoken_text(text)


def normalize_spoken_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for pattern, replacement in _REWRITES:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _word_count(sentence: str) -> int:
    return len(sentence.split())


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    sentence = sentence.strip()
    if not sentence:
        return []
    if _word_count(sentence) <= max_words:
        return [sentence]

    parts: list[str] = []
    for clause in _CLAUSE_SPLIT.split(sentence):
        clause = clause.strip()
        if not clause:
            continue
        if _word_count(clause) <= max_words:
            parts.append(clause if clause[-1] in ".!?" else f"{clause}.")
            continue
        words = clause.split()
        for i in range(0, len(words), max_words):
            chunk = " ".join(words[i : i + max_words]).strip()
            if chunk:
                parts.append(chunk if chunk[-1] in ".!?" else f"{chunk}.")
    return parts or [sentence]


def split_spoken_sentences(text: str, *, max_words: int = 14) -> list[str]:
    normalized = normalize_spoken_text(text)
    if not normalized:
        return []

    raw_sentences = _SENTENCE_SPLIT.split(normalized)
    sentences: list[str] = []
    for raw in raw_sentences:
        raw = raw.strip()
        if not raw:
            continue
        sentences.extend(_split_long_sentence(raw, max_words))

    if not sentences and normalized:
        sentences = _split_long_sentence(normalized, max_words)
    return sentences


def render_speech(
    text: str,
    *,
    max_words: int = 14,
    pause_min_ms: int = 400,
    pause_max_ms: int = 700,
) -> list[SpeechChunk]:
    """Return sentence-level chunks with inter-chunk pauses for TTS."""
    sentences = split_spoken_sentences(text, max_words=max_words)
    if not sentences:
        return []

    pause_span = max(0, pause_max_ms - pause_min_ms)
    step = pause_span // max(1, len(sentences) - 1) if len(sentences) > 1 else 0

    chunks: list[SpeechChunk] = []
    for idx, sentence in enumerate(sentences):
        pause = 0
        if idx < len(sentences) - 1:
            pause = pause_min_ms + (step * idx) % (pause_span + 1)
            pause = min(pause, pause_max_ms)
        chunks.append(SpeechChunk(text=sentence, pause_after_ms=pause))
    return chunks


def render_speech_telephony(text: str, *, max_words: int = 40) -> list[SpeechChunk]:
    """PSTN: lead sentence first (cached/instant), remainder prefetched while speaking."""
    spoken = normalize_spoken_text(text)
    if not spoken:
        return []

    sentences = split_spoken_sentences(spoken, max_words=18)
    if len(sentences) <= 1:
        return [SpeechChunk(text=spoken, pause_after_ms=0)]

    first = sentences[0]
    rest = " ".join(sentences[1:])
    if len(rest.split()) > max_words:
        rest_parts = split_spoken_sentences(rest, max_words=max_words)
        chunks = [SpeechChunk(text=first, pause_after_ms=0)]
        chunks.extend(SpeechChunk(text=part, pause_after_ms=0) for part in rest_parts)
        return chunks

    return [
        SpeechChunk(text=first, pause_after_ms=0),
        SpeechChunk(text=rest, pause_after_ms=0),
    ]


def iter_chunk_texts(texts: Iterable[str], *, telephony: bool = False, **kwargs) -> list[str]:
    """Flatten script lines into unique chunk texts (for TTS warm-cache)."""
    seen: set[str] = set()
    out: list[str] = []
    telephony_max_words = kwargs.get("max_words", 40)
    for text in texts:
        if telephony:
            for chunk in render_speech_telephony(text, max_words=telephony_max_words):
                part = chunk.text.strip()
                if part and part not in seen:
                    seen.add(part)
                    out.append(part)
            continue
        for chunk in render_speech(text, **kwargs):
            line = chunk.text.strip()
            if line and line not in seen:
                seen.add(line)
                out.append(line)
    return out


def silence_pcm(duration_ms: int, sample_rate: int) -> bytes:
    samples = max(0, int(sample_rate * duration_ms / 1000))
    return b"\x00\x00" * samples


if PIPECAT_AVAILABLE:

    @dataclass
    class SpokenChunkFrame(DataFrame):
        """One TTS sentence plus optional trailing pause."""

        text: str
        pause_after_ms: int = 0
        reset_barge_in: bool = False
        prefetch_text: str = ""

    class BargeInProcessor(FrameProcessor):  # type: ignore[misc]
        """Emit ``InterruptionFrame`` when the caller speaks over the bot."""

        def __init__(self, controller: CallController, *, telephony: bool = False):
            super().__init__()
            self._controller = controller
            self._telephony = telephony

        async def _on_caller_started(self, frame, direction) -> None:  # type: ignore[no-untyped-def]
            if self._controller.should_interrupt():
                if self._telephony:
                    # PSTN echo often triggers false barge-in; let the bot finish the line.
                    logger.info("VAD: caller speech during bot playback (telephony — no barge-in)")
                    return
                logger.info("Barge-in: caller speaking over bot — stopping TTS")
                self._controller.on_interruption()
                await self.push_frame(InterruptionFrame(), direction)
            else:
                self._controller.on_listening()

        async def process_frame(self, frame, direction):  # type: ignore[override]
            await super().process_frame(frame, direction)

            if isinstance(frame, VADUserStartedSpeakingFrame):
                logger.info("VAD: caller started speaking")
                await self._on_caller_started(frame, direction)
            elif isinstance(frame, UserStartedSpeakingFrame):
                await self._on_caller_started(frame, direction)
            elif isinstance(frame, VADUserStoppedSpeakingFrame):
                logger.info("VAD: caller stopped speaking — sending audio to STT")

            await self.push_frame(frame, direction)

    class SpeechRendererNode(FrameProcessor):  # type: ignore[misc]
        """FSM/Gemini text -> spoken chunks -> streaming TTS."""

        def __init__(
            self,
            controller: CallController,
            *,
            max_words: int = 14,
            pause_min_ms: int = 400,
            pause_max_ms: int = 700,
            telephony: bool = False,
            telephony_max_words: int = 40,
        ):
            super().__init__()
            self._controller = controller
            self._max_words = max_words
            self._pause_min_ms = pause_min_ms
            self._pause_max_ms = pause_max_ms
            self._telephony = telephony
            self._telephony_max_words = telephony_max_words
            self._cancel_stream = False

        async def process_frame(self, frame, direction):  # type: ignore[override]
            await super().process_frame(frame, direction)

            if isinstance(frame, InterruptionFrame):
                self._cancel_stream = True
                self._controller.on_interruption()
                await self.push_frame(frame, direction)
                return

            if isinstance(frame, BotStoppedSpeakingFrame):
                self._controller.on_bot_stopped()
                await self.push_frame(frame, direction)
                return

            if isinstance(frame, TTSSpeakFrame) and frame.text.strip():
                self._cancel_stream = False
                self._controller.interrupted = False
                if self._telephony:
                    chunks = render_speech_telephony(
                        frame.text,
                        max_words=self._telephony_max_words,
                    )
                else:
                    chunks = render_speech(
                        frame.text,
                        max_words=self._max_words,
                        pause_min_ms=self._pause_min_ms,
                        pause_max_ms=self._pause_max_ms,
                    )
                if not chunks:
                    return

                self._controller.on_response_start()
                logger.debug(f"SpeechRenderer: {len(chunks)} chunk(s) from {frame.text[:48]!r}...")
                for idx, chunk in enumerate(chunks):
                    if self._cancel_stream:
                        break
                    prefetch = chunks[idx + 1].text if idx + 1 < len(chunks) else ""
                    await self.push_frame(
                        SpokenChunkFrame(
                            text=chunk.text,
                            pause_after_ms=chunk.pause_after_ms,
                            reset_barge_in=(idx == 0),
                            prefetch_text=prefetch,
                        ),
                        direction,
                    )
                return

            await self.push_frame(frame, direction)

else:  # pragma: no cover
    SpokenChunkFrame = object  # type: ignore
