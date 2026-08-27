"""Pipecat pipeline wiring: VAD -> STT -> FronterProcessor -> SpeechRenderer -> TTS.

The FronterProcessor turns final transcriptions into bot replies via the conversation engine and
triggers ViciDial actions (warm transfer / disposition) when the FSM decides to.

All bot speech passes through SpeechRendererNode (short spoken chunks + pauses) before TTS.
BargeInProcessor stops TTS when the caller speaks over the bot.

For local testing, pass ``mic_test=True`` to skip ViciDial and use your laptop mic/speakers.

Voice backends (``VOICE_BACKEND`` env):
  - ``managed`` (default): Deepgram STT + Fish Audio TTS — pilot / no GPU
  - ``chatterbox``: faster-whisper STT + Chatterbox Turbo TTS — recommended GPU stack
  - ``gpu``: faster-whisper STT + Piper TTS — legacy / low-quality voice
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Awaitable, Callable

from loguru import logger

from .config import settings, ScriptConfig
from .conversation import (
    Action,
    ConversationEngine,
    _is_consent,
    _is_qualify_yes,
    _looks_like_question,
)
from .fish_tts import FishAudioTTSService
from .gemini import FALLBACK_REPLY, TELEPHONY_KB_MISS_REPLY
from .knowledge import answer_offscript
from .speech_renderer import (
    BargeInProcessor,
    CallController,
    CallState,
    RtpKeepaliveStartFrame,
    RtpKeepaliveStopFrame,
    SpeechRendererNode,
    iter_chunk_texts,
    prepare_for_speech,
    render_speech,
)
from .vicidial import ViciDialClient

try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.frames.frames import (
        AudioRawFrame,
        BotStoppedSpeakingFrame,
        EndFrame,
        InputAudioRawFrame,
        InterimTranscriptionFrame,
        InterruptionFrame,
        StartFrame,
        SystemFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.processors.audio.vad_processor import VADProcessor
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.services.deepgram.stt import DeepgramSTTService
    PIPECAT_AVAILABLE = True
except Exception:  # pragma: no cover - allows the FSM/tests to run without Pipecat installed
    PIPECAT_AVAILABLE = False
    FrameProcessor = object  # type: ignore


_STT_IGNORE = frozenset({
    "you",
    "the",
    "a",
    "an",
    "oh",
    "um",
    "uh",
    "hmm",
    "bye",
    "thanks",
    "thank you",
    ".",
    "..",
    "...",
})


_STT_GREETING_FIXES = {
    "i'm dead": "I'm good",
    "im dead": "I'm good",
    "i am dead": "I am good",
    "i'm good.": "I'm good",
    "yes.": "yes",
    "yeah.": "yeah",
    "yep.": "yep",
    "no.": "no",
    "nope.": "nope",
    "okay.": "okay",
    "ok.": "okay",
    "hello.": "hello",
    "hi.": "hi",
}


def _normalize_caller_stt(text: str) -> str:
    key = text.strip().lower().rstrip(".")
    return _STT_GREETING_FIXES.get(key, text)


_CANT_HEAR_MARKERS = (
    "can't hear",
    "cannot hear",
    "can you hear",
    "can't fear",  # common STT mangling of "can't hear"
    "can't share you",
    "i don't hear",
    "not hearing",
)


def _is_cant_hear(text: str) -> bool:
    u = (text or "").strip().lower()
    return any(marker in u for marker in _CANT_HEAR_MARKERS)


def _is_meaningful_caller_text(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 2:
        return False
    if t in _STT_IGNORE:
        return False
    words = [w for w in t.replace(",", " ").split() if w]
    # Bare ages ("65", "82") must pass — single 2-digit tokens were dropped before.
    if len(words) == 1 and words[0].isdigit() and 18 <= int(words[0]) <= 120:
        return True
    if len(words) == 1 and len(words[0]) <= 2 and words[0] not in {"no", "yes"}:
        return False
    return True


_WHISPER_PHANTOM_UTTERANCES = frozenset(
    {
        "thank you",
        "thanks",
        "thank you.",
        "thanks.",
        "thank you thank you",
        "thanks for watching",
        "you",
        "you can",
        "you can.",
        "the",
        "a",
        "uh",
        "um",
    }
)


def _normalize_echo_text(text: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_whisper_phantom(text: str) -> bool:
    """Drop common false STT (silence/echo hallucinations), not real answers."""
    t = _normalize_echo_text(text)
    if not t:
        return True
    if t in _WHISPER_PHANTOM_UTTERANCES:
        return True
    # "Thank you. Thank you." / repeated thanks only
    thanks_only = t.replace("thank you", " ").replace("thanks", " ").strip()
    if not thanks_only and "thank" in t:
        return True
    return False


def _is_likely_bot_echo(text: str, bot_reply: str) -> bool:
    """True when STT is the bot hearing itself (e.g. 'you can' from 'you qualify')."""
    t = _normalize_echo_text(text)
    b = _normalize_echo_text(bot_reply)
    if not t or not b:
        return False
    if t in b:
        return True
    t_words = t.split()
    b_words = b.split()
    b_set = set(b_words)
    if not t_words:
        return False

    def _word_in_bot(w: str) -> bool:
        if len(w) <= 2:
            return True
        if w in b_set:
            return True
        # Partial hear: "can" inside "qualify", "med" from "medicare"
        return any(
            (len(bw) >= 4 and (bw.startswith(w) or w in bw))
            for bw in b_words
        )

    # Short fragment whose words all appear (or are prefixes) in the bot line.
    if len(t_words) <= 4:
        content = [w for w in t_words if len(w) > 2]
        if content and all(_word_in_bot(w) for w in content):
            return True
    # High token overlap for slightly longer mis-hears of the same sentence.
    content = [w for w in t_words if len(w) > 2]
    if len(content) >= 2:
        overlap = sum(1 for w in content if _word_in_bot(w))
        if overlap >= max(2, int(len(content) * 0.75)):
            return True
    return False


def should_telephony_barge_in(text: str, engine: ConversationEngine) -> bool:
    """Stop bot playback on PSTN when the caller asks a real question (KB or off-script)."""
    normalized = _normalize_caller_stt(text)
    if not _is_meaningful_caller_text(normalized):
        return False
    if _looks_like_question(normalized):
        return True
    return bool(engine._kb_only_answer(normalized))


class FronterProcessor(FrameProcessor):  # type: ignore[misc]
    def __init__(
        self,
        engine: ConversationEngine,
        vicidial: ViciDialClient | None,
        agent_user: str,
        *,
        mic_test: bool = False,
        call_controller: CallController | None = None,
        telephony: bool = False,
        telephony_phone_test: bool = False,
        vicidial_call_id: str | None = None,
        transfer_preset: str | None = None,
        on_call_should_end: Callable[[str], Awaitable[None]] | None = None,
        is_call_active: Callable[[], bool] | None = None,
    ):
        super().__init__()
        self._engine = engine
        self._vici = vicidial
        self._agent_user = agent_user
        self._vicidial_call_id = (vicidial_call_id or "").strip() or None
        self._transfer_preset = (transfer_preset or "").strip() or None
        self._mic_test = mic_test
        self._telephony = telephony
        self._telephony_phone_test = telephony_phone_test
        self._on_call_should_end = on_call_should_end
        self._is_call_active = is_call_active
        self._opened = False
        self._call = call_controller or CallController()
        self._pending_caller_texts: list[str] = []
        self._followup_reply: str | None = None
        self._caller_buffer: str = ""
        self._flush_task: asyncio.Task | None = None
        # Short flush: VAD already ended the utterance; long delay pads first reply.
        self._caller_flush_delay_s = 0.12 if (telephony or telephony_phone_test) else 0.75
        self.last_activity_monotonic: float = time.monotonic()
        self._telephony_send_json: Callable[[str], Awaitable[None]] | None = None
        self._telephony_tts: object | None = None
        self._telephony_encoding: str = "PCMU"
        self._telephony_direct_media = False
        self._bot_audio_until: float = 0.0
        self._discard_early_ack_after_play = False

    def _bot_reference_text(self) -> str:
        parts = [
            self._engine._last_reply or "",
            self._followup_reply or "",
            self.script_pitch_hint() if hasattr(self, "script_pitch_hint") else "",
        ]
        return " ".join(p for p in parts if p)

    def script_pitch_hint(self) -> str:
        return (self._engine.script.pitch or "") + " " + (self._engine.script.greeting or "")

    def _should_drop_stt_as_echo(self, text: str) -> bool:
        """Drop bot-loopback / Whisper phantoms so fake 'Thank you' never advances the script."""
        if not self._telephony:
            return False
        if _is_whisper_phantom(text):
            return True
        bot = self._bot_reference_text()
        if bot and _is_likely_bot_echo(text, bot):
            return True
        # Acoustic tail after bot audio — short phantoms are almost always echo.
        if self._bot_audio_until and time.monotonic() < self._bot_audio_until:
            t = _normalize_echo_text(text)
            from .conversation import _extract_age_years

            # Never drop a real age during the echo tail.
            if _extract_age_years(text) is not None:
                return False
            # Age preamble fragments ("I am" / "I'm") — wait for the number.
            if t in {"i am", "im", "i m", "i'm"} or t.endswith(" years old"):
                return False
            # Mid-playback "yes"/"okay"/"hello" are usually echo or impatience.
            # Real answers are accepted after the turn opens.
            if len(t.split()) <= 4 and not _is_cant_hear(text):
                return True
        return False

    def _mark_bot_audio_window(self, duration_ms: int = 0) -> None:
        # Hold off STT briefly after speech so line echo is not treated as the caller.
        tail_s = 0.55
        self._bot_audio_until = time.monotonic() + max(0, duration_ms) / 1000.0 + tail_s

    def set_direct_telephony_media(
        self,
        *,
        send_json: Callable[[str], Awaitable[None]],
        tts: object | None = None,
        encoding: str = "PCMU",
    ) -> None:
        """Wire the AudioSocket/Telnyx WS sender so FSM replies use the same bulk PCM path as greeting."""
        self._telephony_send_json = send_json
        self._telephony_tts = tts
        self._telephony_encoding = (encoding or "PCMU").strip() or "PCMU"
        self._telephony_direct_media = True

    async def _speak_bot_text(self, text: str) -> None:
        """Play bot reply — direct bulk PCM on ViciDial, else pipeline TTS."""
        reply = (text or "").strip()
        if not reply:
            return
        if (
            self._telephony_direct_media
            and self._telephony_send_json is not None
            and self._telephony_tts is not None
        ):
            from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
            from .speech_renderer import render_speech_telephony
            from .telnyx_media import (
                _synthesize_line,
                greeting_pcm_from_cache,
                send_direct_bulk_pcm,
            )
            from .call_trace import trace_call

            # Stay PROCESSING while synthesizing — do NOT enter SPEAKING until
            # PCM is ready. Entering SPEAKING early caused post–Part A silence
            # while STT queued, then a qualify burst on BSSF.
            self._call.on_processing()
            self._touch_activity()

            chunks = render_speech_telephony(
                reply, max_words=settings.telephony_utterance_max_words
            )
            if not chunks:
                from .speech_renderer import SpeechChunk

                chunks = [SpeechChunk(text=reply, pause_after_ms=0)]

            prepared: list[tuple[str, bytes]] = []
            for chunk in chunks:
                line = chunk.text.strip()
                if not line:
                    continue
                pcm = greeting_pcm_from_cache(
                    self._telephony_tts,
                    line,
                    telephony_max_words=settings.telephony_utterance_max_words,
                )
                if not pcm:
                    pcm = _synthesize_line(line, tts=self._telephony_tts)
                    if pcm is not None:
                        cache = getattr(self._telephony_tts, "_cache", None)
                        if isinstance(cache, dict):
                            cache[line] = pcm
                if not pcm:
                    trace_call(
                        f"=== WARNING: no PCM for sentence — skipping: {line[:72]!r} ==="
                    )
                    continue
                prepared.append((line, pcm))

            if not prepared:
                trace_call(
                    f"=== WARNING: no direct PCM for full reply — pipeline TTS: "
                    f"{reply[:72]!r} ==="
                )
                # Keep turn closed until pipeline TTS BSSF (do not complete early).
                self._call.begin_bot_reply(1)
                if PIPECAT_AVAILABLE:
                    await self.push_frame(RtpKeepaliveStopFrame())
                await self.push_frame(TTSSpeakFrame(reply))
                return

            # Short qualify asks: discard mid-synth "yes"/"okay" after play so they
            # do not auto-answer the question the caller never heard.
            self._discard_early_ack_after_play = len(reply.split()) <= 14

            self._call.begin_bot_reply(1)
            self._touch_activity()
            if PIPECAT_AVAILABLE:
                await self.push_frame(RtpKeepaliveStopFrame())

            sent_any = False
            for line, pcm in prepared:
                duration_ms = await send_direct_bulk_pcm(
                    self._telephony_send_json,
                    pcm,
                    sample_rate=TELEPHONY_PIPELINE_RATE,
                    encoding=self._telephony_encoding,
                    pace=False,
                )
                if duration_ms <= 0:
                    trace_call(f"=== WARNING: direct reply 0ms: {line[:72]!r} ===")
                    continue
                self._mark_bot_audio_window(duration_ms)
                await asyncio.sleep(duration_ms / 1000.0)
                trace_call(f"=== direct reply sent (~{duration_ms}ms): {line[:72]!r} ===")
                sent_any = True

            if not sent_any:
                trace_call(
                    f"=== WARNING: direct PCM send failed — pipeline TTS: "
                    f"{reply[:72]!r} ==="
                )
                await self.push_frame(TTSSpeakFrame(reply))
                return

            await self._complete_direct_bot_playback()
            return
        await self.push_frame(TTSSpeakFrame(reply))

    def _touch_activity(self) -> None:
        self.last_activity_monotonic = time.monotonic()

    def _call_live(self) -> bool:
        return self._is_call_active is None or self._is_call_active()

    async def _start_telephony_keepalive(self) -> None:
        if self._telephony and PIPECAT_AVAILABLE:
            await self.push_frame(RtpKeepaliveStartFrame())

    async def _complete_direct_bot_playback(self) -> None:
        """End direct bulk PCM the same way pipeline TTS ends (local BSSF handling).

        push_frame(BSSF, DOWNSTREAM) never reaches this processor — follow-ups stayed
        silent and STT queued mid-utterance dumped later as a rapid qualify burst.
        """
        self._touch_activity()
        # After short qualify asks, drop bare mid-playback yes/okay/hello so they
        # don't auto-answer a question the caller hasn't heard. Keep "Yes, I do"
        # / age numbers (not early-ack-only).
        if self._discard_early_ack_after_play and self._pending_is_early_ack_only():
            dropped = len(self._pending_caller_texts)
            self._pending_caller_texts.clear()
            self._discard_early_ack_after_play = False
            if dropped and self._telephony:
                from .call_trace import trace_call

                trace_call(
                    f"=== discarded {dropped} early-ack STT after qualify ask "
                    "(waiting for real answer) ==="
                )
        else:
            self._discard_early_ack_after_play = False
        await self._start_telephony_keepalive()
        if self._telephony:
            from .call_trace import trace_call

            trace_call(
                f"=== bot playback complete (direct) pending={len(self._pending_caller_texts)} "
                f"followup={bool(self._followup_reply)} ==="
            )
        if not PIPECAT_AVAILABLE:
            self._call.finish_bot_playback()
            self._move_pending_to_buffer()
            if self._caller_buffer.strip():
                self._schedule_caller_flush()
            return
        from pipecat.frames.frames import BotStoppedSpeakingFrame
        from pipecat.processors.frame_processor import FrameDirection

        await self.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    async def on_direct_greeting_complete(self) -> None:
        """Opening line played via direct bulk PCM — match normal TTS end-of-playback."""
        logger.info("Direct bulk greeting finished — releasing caller turn")
        # Drop STT captured during the greeting (echo of our own voice) so we do not
        # jump straight into the pitch without hearing the caller.
        dropped = len(self._pending_caller_texts) + (
            1 if self._caller_buffer.strip() else 0
        )
        self._pending_caller_texts.clear()
        self._caller_buffer = ""
        self._cancel_flush_task()
        if dropped and self._telephony:
            from .call_trace import trace_call

            trace_call(
                f"=== greeting done — discarded {dropped} echo STT fragment(s); waiting for caller ==="
            )
        await self._complete_direct_bot_playback()

    async def _interrupt_and_handle_caller(self, text: str, direction) -> None:  # type: ignore[no-untyped-def]
        """Stop current TTS and answer the caller immediately (telephony KB/questions)."""
        logger.info(f"Telephony barge-in — answering caller: {text[:64]!r}")
        self._cancel_flush_task()
        self._followup_reply = None
        self._call.on_interruption()
        await self.push_frame(InterruptionFrame(), direction)
        await asyncio.sleep(0.05)
        self._call.finish_bot_playback()
        await self._start_telephony_keepalive()
        await self._handle_caller(_normalize_caller_stt(text))

    def _maybe_barge_in_for_caller(self, text: str) -> bool:
        return self._telephony and should_telephony_barge_in(text, self._engine)

    def _merge_transcripts(self, prev: str, new: str) -> str:
        prev_s, new_s = prev.strip(), new.strip()
        if not prev_s:
            return new_s
        if not new_s:
            return prev_s
        pl, nl = prev_s.lower(), new_s.lower()
        if nl in pl:
            return prev_s
        if pl in nl:
            return new_s
        # "I am." + "61" / "I am" + "92" → one age answer for the qualify FSM.
        from .conversation import _extract_age_years

        if _extract_age_years(prev_s) is None and _extract_age_years(new_s) is not None:
            if pl.rstrip(".!") in {"i am", "i'm", "im", "age", "years"} or pl.endswith(
                ("i am", "i'm", "im")
            ):
                return f"{prev_s.rstrip('.!')} {new_s}".strip()
        if _extract_age_years(f"{prev_s} {new_s}") is not None:
            if _extract_age_years(prev_s) is None or _extract_age_years(new_s) is None:
                return f"{prev_s} {new_s}".strip()
        # Keep both — never drop an earlier answer for a longer clarification.
        return f"{prev_s} {new_s}"

    def _buffer_caller_text(self, text: str) -> None:
        if not text.strip():
            return
        self._caller_buffer = self._merge_transcripts(self._caller_buffer, text)

    def _has_pending_caller(self) -> bool:
        return bool(self._pending_caller_texts) or bool(self._caller_buffer.strip())

    def _cancel_flush_task(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = None

    def _schedule_caller_flush(self) -> None:
        if not PIPECAT_AVAILABLE:
            return
        self._cancel_flush_task()

        async def _delayed_flush() -> None:
            try:
                await asyncio.sleep(self._caller_flush_delay_s)
                await self._flush_caller_buffer()
            except asyncio.CancelledError:
                pass

        self._flush_task = asyncio.create_task(_delayed_flush())

    async def _flush_caller_buffer(self) -> None:
        self._cancel_flush_task()
        if not self._call.can_accept_caller():
            # Turn still closed (bot still speaking) — retry shortly; don't orphan.
            if self._caller_buffer.strip():
                self._schedule_caller_flush()
            return
        text = self._caller_buffer.strip()
        self._caller_buffer = ""
        if not _is_meaningful_caller_text(text):
            logger.info(f"Ignoring low-confidence STT fragment: {text!r}")
            return
        if self._should_drop_stt_as_echo(text):
            logger.info(f"STT echo/phantom dropped on flush: {text[:64]!r}")
            if self._telephony:
                from .call_trace import trace_call

                trace_call(f"=== STT echo dropped: {text[:80]!r} ===")
            return
        self._call.close_user_turn()
        await self._handle_caller(text)

    def _queue_pending_caller_text(self, text: str) -> None:
        if not _is_meaningful_caller_text(text):
            return
        cleaned = text.strip()
        if not cleaned:
            return
        if self._should_drop_stt_as_echo(cleaned):
            logger.info(f"STT echo/phantom dropped (bot speaking): {cleaned[:64]!r}")
            if self._telephony:
                from .call_trace import trace_call

                trace_call(f"=== STT echo dropped: {cleaned[:80]!r} ===")
            return
        # If the caller turn is already open, never leave speech stuck in the
        # mid-utterance queue (that caused silence, then Hello? skipping Yes).
        if self._call.can_accept_caller():
            self._buffer_caller_text(cleaned)
            self._schedule_caller_flush()
            if self._telephony:
                from .call_trace import trace_call

                trace_call(f"=== STT late-flush (turn open): {cleaned[:80]!r} ===")
            return
        # Queue each distinct utterance — do not overwrite earlier answers.
        if self._pending_caller_texts:
            last = self._pending_caller_texts[-1].lower()
            if cleaned.lower() in last or last in cleaned.lower():
                if len(cleaned) > len(self._pending_caller_texts[-1]):
                    self._pending_caller_texts[-1] = cleaned
                logger.info(
                    "STT heard caller while bot speaking — queued: "
                    f"{self._pending_caller_texts[-1][:64]!r}"
                )
                return
        self._pending_caller_texts.append(cleaned)
        logger.info(
            "STT heard caller while bot speaking — queued: "
            f"{cleaned[:64]!r} ({len(self._pending_caller_texts)} waiting)"
        )
        if self._telephony:
            from .call_trace import trace_call

            trace_call(f"=== STT queued (bot speaking): {cleaned[:80]!r} ===")

    def _utterance_priority(self, item: str) -> int:
        # Prefer real answers (age / yes) over "What?" / "Hello?" when several STT fragments queued.
        from .conversation import _extract_age_years

        if _extract_age_years(item) is not None:
            return 4
        t = item.strip().lower().rstrip(".!?")
        if t in ("yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "correct"):
            return 3
        if _is_consent(item):
            return 2
        if t in ("hello", "hi", "hey", "you there", "are you there"):
            return 0
        if _looks_like_question(item):
            return 1
        return 0

    def _pending_is_early_ack_only(self) -> bool:
        """True when queued STT is only yes/okay/hello — not an age answer or real question."""
        from .conversation import _extract_age_years

        if not self._pending_caller_texts:
            return False
        for item in self._pending_caller_texts:
            if _is_cant_hear(item):
                continue  # treat as noise — still play the scripted follow-up
            if _extract_age_years(item) is not None:
                return False
            t = item.strip().lower().rstrip(".!?")
            if t in (
                "yes",
                "yeah",
                "yep",
                "sure",
                "ok",
                "okay",
                "go ahead",
                "correct",
                "hello",
                "hi",
                "hey",
            ):
                continue
            if _is_consent(item):
                continue
            # "Yes, I do" / "Yes, I have" are real qualify answers — keep them.
            if _looks_like_question(item) and t not in ("hello", "hi", "hey"):
                return False
            if len(t.split()) > 2 and t not in ("are you there", "you there"):
                return False
        return True

    def _collapse_caller_queue(self) -> str | None:
        """Pick the strongest signal when the caller spoke over the bot multiple times."""
        if not self._pending_caller_texts:
            return None
        items = [t for t in self._pending_caller_texts if not _is_cant_hear(t)]
        if not items:
            # Only "can't hear you" — clear and let caller turn re-open / repeat path.
            self._pending_caller_texts.clear()
            return None
        self._pending_caller_texts.clear()
        best_idx = max(range(len(items)), key=lambda i: (self._utterance_priority(items[i]), i))
        chosen = items[best_idx]
        if len(items) > 1:
            logger.info(
                f"STT queue collapsed {len(items)} utterances — using: {chosen[:64]!r}"
            )
        return _normalize_caller_stt(chosen)

    def _move_pending_to_buffer(self) -> None:
        if not self._pending_caller_texts:
            return
        next_text = self._collapse_caller_queue()
        if not next_text:
            return
        self._caller_buffer = next_text

    async def _handle_caller(self, text: str) -> None:
        text = _normalize_caller_stt(text)
        self._call.close_user_turn()
        self._call.on_processing()
        await self._start_telephony_keepalive()
        logger.info(f"CALLER: {text}")
        if self._telephony:
            from .call_trace import trace_call

            trace_call(f"=== CALLER: {text[:120]!r} ===")

        # Caller can't hear bot audio — repeat last line instead of KB/qualify skip.
        if self._telephony and _is_cant_hear(text):
            repeat = (self._engine._last_reply or self._followup_reply or "").strip()
            if repeat:
                from .call_trace import trace_call

                trace_call(f"=== can't-hear — repeating last bot line: {repeat[:72]!r} ===")
                self._followup_reply = self._followup_reply or None
                await self._speak_bot_text(repeat)
                return

        turn = self._engine.handle(text)
        spoken = render_speech(turn.reply)
        logger.info(f"BOT: {' | '.join(c.text for c in spoken) or turn.reply}")
        if self._telephony:
            from .call_trace import trace_call

            trace_call(f"=== BOT: {(turn.reply or '')[:240]!r} ===")
        followup = self._engine.take_pending_followup()
        self._followup_reply = followup or None
        if followup:
            logger.info(f"BOT follow-up queued: {followup[:64]!r}")
        await self._speak_bot_text(turn.reply)

        if turn.action == Action.TRANSFER:
            if self._mic_test:
                logger.info("MIC TEST -> qualified lead (warm transfer simulated)")
            else:
                await self._execute_transfer()
            if not self._telephony_phone_test:
                await self.push_frame(EndFrame())
        elif turn.action == Action.HANGUP:
            if self._mic_test:
                logger.info("MIC TEST -> call ended (hangup simulated)")
            else:
                await self._execute_hangup()
            # Keep Telnyx media alive during phone tests so a disposition line
            # does not tear down the stream before the caller hears it.
            if not self._telephony_phone_test:
                await self.push_frame(EndFrame())

    @staticmethod
    def _transfer_extension(closer: str | None) -> str | None:
        token = (closer or "").strip()
        if not token:
            return None
        if token.startswith("+") or token.isdigit():
            return token
        digits = "".join(ch for ch in token if ch.isdigit())
        return digits if len(digits) >= 3 else None

    async def _execute_transfer(self) -> None:
        if self._vici is None:
            logger.warning("Transfer skipped — no ViciDial client (check Integrations / .env)")
            return
        closer = (self._engine.script.transfer_closer_user or "").strip()
        preset = (
            (self._engine.script.transfer_preset or "").strip()
            or self._transfer_preset
            or settings.vicidial_transfer_preset
        )

        if self._vicidial_call_id:
            extension = self._transfer_extension(closer)
            if extension:
                logger.info(
                    f"FSM -> remote-agent EXTENSIONTRANSFER ext={extension} "
                    f"call_id={self._vicidial_call_id}"
                )
                if self._telephony:
                    from .call_trace import trace_call

                    trace_call(
                        f"=== INGROUPTRANSFER skipped (using EXTENSIONTRANSFER "
                        f"ext={extension} call_id={self._vicidial_call_id}) ==="
                    )
                result = await self._vici.remote_agent_transfer(
                    self._agent_user,
                    self._vicidial_call_id,
                    extension=extension,
                    status="XFER",
                )
            else:
                ingroup = preset or "DEFAULTINGROUP"
                logger.info(
                    f"FSM -> remote-agent INGROUPTRANSFER ingroup={ingroup} "
                    f"call_id={self._vicidial_call_id}"
                )
                if self._telephony:
                    from .call_trace import trace_call

                    trace_call(
                        f"=== INGROUPTRANSFER ingroup={ingroup} "
                        f"call_id={self._vicidial_call_id} ==="
                    )
                result = await self._vici.remote_agent_transfer(
                    self._agent_user,
                    self._vicidial_call_id,
                    ingroup=ingroup,
                    status="XFER",
                )
            if not ViciDialClient.api_succeeded(result):
                logger.error(f"Remote-agent transfer failed: {result[:200]}")
            return

        if self._telephony:
            from .call_trace import trace_call

            trace_call(
                "=== WARNING: transfer with no vicidial_call_id — "
                "trying agent-seat warm_transfer (often fails for remote agent) ==="
            )
        if closer:
            logger.info(f"FSM -> warm transfer to closer {closer}")
            result = await self._vici.warm_transfer(self._agent_user, closer_user=closer)
        else:
            logger.info(f"FSM -> warm transfer (preset={preset})")
            result = await self._vici.warm_transfer(self._agent_user, preset=preset)
        await self._vici.set_disposition(self._agent_user, "XFER")
        if not ViciDialClient.api_succeeded(result):
            logger.error(f"Warm transfer failed: {result[:200]}")
            if self._telephony:
                from .call_trace import trace_call

                trace_call(f"=== WARNING: warm transfer failed: {result[:160]} ===")

    async def _execute_hangup(self) -> None:
        if self._vici is None:
            logger.warning("Hangup skipped — no ViciDial client")
            return
        if self._vicidial_call_id:
            logger.info(f"FSM -> remote-agent HANGUP call_id={self._vicidial_call_id}")
            result = await self._vici.remote_agent_hangup(
                self._agent_user, self._vicidial_call_id, status="NI"
            )
            if not ViciDialClient.api_succeeded(result):
                logger.error(f"Remote-agent hangup failed: {result[:200]}")
            return
        logger.info("FSM -> disposition + hangup")
        await self._vici.set_disposition(self._agent_user, "NI")
        await self._vici.hangup(self._agent_user)

    async def process_frame(self, frame, direction):  # type: ignore[override]
        await super().process_frame(frame, direction)

        # Mic audio must not reach TTS — only STT/VAD consume it upstream.
        if isinstance(frame, (InputAudioRawFrame, AudioRawFrame)):
            return

        if isinstance(frame, StartFrame):
            if not self._opened:
                self._opened = True
                self._call.state = CallState.LISTENING
                opening = self._engine.open()
                spoken = render_speech(opening.reply)
                logger.info(f"BOT: {' | '.join(c.text for c in spoken) or opening.reply}")
                await self.push_frame(TTSSpeakFrame(opening.reply))
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterruptionFrame):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterimTranscriptionFrame):
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            # Scripted follow-up (Part A/B after pitch body) beats early yes/hello so the
            # caller hears the question; their queued Yes answers it on the next BSSF.
            if (
                self._followup_reply
                and self._pending_caller_texts
                and self._pending_is_early_ack_only()
            ):
                logger.info(
                    "Keeping bot follow-up — queued STT is early ack only "
                    f"({len(self._pending_caller_texts)} waiting)"
                )
            elif self._pending_caller_texts:
                if self._followup_reply:
                    logger.info(
                        "Dropping bot follow-up — caller has queued speech waiting"
                    )
                    self._followup_reply = None
                if not self._call.can_accept_caller():
                    self._call.finish_bot_playback()
                await self._start_telephony_keepalive()
                logger.info("Bot playback done — releasing queued caller audio")
                self._move_pending_to_buffer()
                if self._caller_buffer:
                    self._schedule_caller_flush()
                await self.push_frame(frame, direction)
                return
            if self._followup_reply:
                followup = self._followup_reply
                self._followup_reply = None
                spoken = render_speech(followup)
                logger.info(
                    f"BOT follow-up: {' | '.join(c.text for c in spoken) or followup}"
                )
                self._call.on_processing()
                await self._speak_bot_text(followup)
                await self.push_frame(frame, direction)
                return
            if not self._call.can_accept_caller():
                self._call.finish_bot_playback()
            if self._call.can_accept_caller():
                if self._pending_caller_texts or self._caller_buffer.strip():
                    await self._start_telephony_keepalive()
                self._move_pending_to_buffer()
                if self._caller_buffer:
                    self._schedule_caller_flush()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if self._pending_caller_texts and self._call.can_accept_caller():
                self._move_pending_to_buffer()
            if self._call.can_accept_caller() and self._caller_buffer:
                await self._flush_caller_buffer()
            elif self._caller_buffer:
                self._schedule_caller_flush()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, (EndFrame, SystemFrame)):
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text:
            text = frame.text.strip()
            if not text:
                return

            if not self._call.can_accept_caller():
                if self._call.state in (CallState.SPEAKING, CallState.PROCESSING):
                    if self._maybe_barge_in_for_caller(text):
                        await self._interrupt_and_handle_caller(text, direction)
                        return
                    self._queue_pending_caller_text(text)
                elif self._pending_caller_texts:
                    self._queue_pending_caller_text(text)
                else:
                    logger.info(
                        f"STT held (turn closed, state={self._call.state.value}): "
                        f"{text[:64]!r}"
                    )
                    if self._telephony:
                        from .call_trace import trace_call

                        trace_call(
                            f"=== STT held (state={self._call.state.value}): "
                            f"{text[:80]!r} ==="
                        )
                return

            if not _is_meaningful_caller_text(text):
                return

            if self._should_drop_stt_as_echo(text):
                logger.info(f"STT echo/phantom dropped: {text[:64]!r}")
                if self._telephony:
                    from .call_trace import trace_call

                    trace_call(f"=== STT echo dropped: {text[:80]!r} ===")
                return

            # Drain mid-bot STT before accepting new audio — prefer Yes over Hello?.
            if self._pending_caller_texts:
                self._pending_caller_texts.append(text.strip())
                merged = self._collapse_caller_queue()
                if merged:
                    self._caller_buffer = merged
                    logger.info(f"STT merged with mid-bot queue: {merged[:64]!r}")
                    if self._telephony:
                        from .call_trace import trace_call

                        trace_call(f"=== STT merged pending: {merged[:80]!r} ===")
                    self._schedule_caller_flush()
                return

            self._buffer_caller_text(text)
            logger.info(f"STT buffered caller text: {text[:64]!r}")
            if self._telephony:
                from .call_trace import trace_call

                trace_call(f"=== STT buffered: {text[:80]!r} ===")
            self._schedule_caller_flush()
            return

        await self.push_frame(frame, direction)


def _speech_settings(*, telephony: bool = False) -> tuple[int, int, int]:
    if telephony:
        return (
            settings.telephony_speech_max_words,
            settings.telephony_pause_min_ms,
            settings.telephony_pause_max_ms,
        )
    return (
        settings.speech_max_words,
        settings.speech_pause_min_ms,
        settings.speech_pause_max_ms,
    )


def _script_cache_lines(script: ScriptConfig, *, telephony: bool = False) -> list[str]:
    max_words, pause_min, pause_max = _speech_settings(telephony=telephony)
    if telephony:
        # Must match SpeechRendererNode (telephony_utterance_max_words), not speech_max_words.
        max_words = settings.telephony_utterance_max_words
    engine = ConversationEngine(script=script)
    consent_q = engine._pitch_consent_question()
    # Match live `_deliver_pitch`: statement + Part A/B in one spoken turn.
    pitch_body, pitch_embedded = engine._pitch_statement_and_first_question()
    from .conversation import _ensure_part_a_first, _looks_like_medicare_script, _PART_A_QUESTION

    medicare = _looks_like_medicare_script(script)
    questions = _ensure_part_a_first(list(script.qualifying_questions), medicare=medicare)
    if pitch_embedded and not questions:
        questions = [pitch_embedded]
    joined_pitch = pitch_body
    if questions:
        first = questions[0]
        if not first.endswith("?"):
            first = f"{first}?"
        if first.lower() not in (pitch_body or "").lower():
            joined_pitch = f"{(pitch_body or '').rstrip(' .!?')}. {first}".strip()

    lines = [
        script.greeting,
        script.pitch,
        joined_pitch,
        pitch_body,
        engine._consent_prompt(),
        engine._short_prompt,
        *questions,
        _PART_A_QUESTION,
        *script.qualifying_questions,
        "Sorry — what age are you?",
        "Sorry — could you say yes or no?",
    ]
    # Pitch is spoken as body + consent follow-up — warm both so first reply isn't silent.
    if consent_q and "?" in (script.pitch or ""):
        pitch = prepare_for_speech(script.pitch)
        pos = pitch.lower().rfind(consent_q.strip().lower())
        if pos >= 0:
            body = pitch[:pos].strip().rstrip(".—-,; ")
            if body:
                lines.append(body)
        lines.append(consent_q if consent_q.endswith("?") else f"{consent_q}?")
    lines.extend([script.transfer_line, script.not_interested_line])
    for entry in script.knowledge_base:
        answer = prepare_for_speech(entry.answer)
        if not answer:
            continue
        lines.append(answer)
        if telephony:
            lines.append(f"{answer} {consent_q}")
            lines.append(f"{answer} {engine._short_prompt}")
            for question in questions:
                lines.append(f"{answer} {question}")
    if telephony:
        lines.append(TELEPHONY_KB_MISS_REPLY)
        lines.append(FALLBACK_REPLY)
    raw = [line.strip() for line in lines if line and line.strip()]
    return iter_chunk_texts(
        raw,
        telephony=telephony,
        max_words=max_words,
        pause_min_ms=pause_min,
        pause_max_ms=pause_max,
    )


def _is_chatterbox_backend() -> bool:
    return settings.voice_backend == "chatterbox"


def _is_piper_backend() -> bool:
    return settings.voice_backend == "gpu"


def _inference_pool_enabled() -> bool:
    from .inference_client import inference_pool_enabled

    return inference_pool_enabled()


def _is_local_gpu_backend() -> bool:
    return _is_chatterbox_backend() or _is_piper_backend()


def _require_api_keys() -> None:
    missing = []
    if not settings.google_api_key:
        missing.append("GOOGLE_API_KEY")
    if _is_local_gpu_backend():
        if _is_chatterbox_backend():
            try:
                from .chatterbox_paths import resolve_chatterbox_reference

                resolve_chatterbox_reference(settings.chatterbox_reference_audio or None)
            except FileNotFoundError as exc:
                raise RuntimeError(str(exc)) from exc
        elif _is_piper_backend():
            try:
                from .piper_paths import resolve_piper_exe, resolve_piper_model

                resolve_piper_exe(settings.piper_exe or None)
                resolve_piper_model(settings.piper_model or None)
            except FileNotFoundError as exc:
                raise RuntimeError(str(exc)) from exc
    else:
        if not settings.deepgram_api_key:
            missing.append("DEEPGRAM_API_KEY")
        if not settings.fish_api_key:
            missing.append("FISH_AUDIO_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing API keys for live mode: "
            + ", ".join(missing)
            + ". Add them to dashboard/.env.local or agent/.env.local."
        )


def _telephony_vad_params() -> VADParams:
    """PSTN audio is quieter and noisier than a laptop mic — relax Silero thresholds."""
    return VADParams(
        confidence=0.35,
        start_secs=0.12,
        # End utterance sooner for faster first reply (bridge keeps the call up now).
        stop_secs=0.28,
        # 0.25 was too high for AudioSocket/ulaw — VAD never fired, so no STT/CALLER.
        min_volume=0.08,
    )


def _build_vad(*, telephony: bool = False) -> VADProcessor:
    params = _telephony_vad_params() if telephony else VADParams(stop_secs=0.5)
    return VADProcessor(
        vad_analyzer=SileroVADAnalyzer(params=params),
        audio_idle_timeout=2.0 if telephony else 1.0,
    )


def _build_stt(*, telephony: bool = False):
    if _is_local_gpu_backend():
        no_speech_prob = 0.55 if telephony else 0.4
        if _inference_pool_enabled():
            from .pooled_stt import PooledWhisperSTTService

            return PooledWhisperSTTService(no_speech_prob=no_speech_prob)

        from pipecat.services.whisper.stt import WhisperSTTService
        from pipecat.transcriptions.language import Language

        from .shared_whisper_stt import SharedModelWhisperSTTService

        logger.info(
            f"STT: faster-whisper ({settings.whisper_model}, "
            f"device={settings.whisper_device}, compute={settings.whisper_compute_type}, "
            f"telephony={telephony}, no_speech_prob={no_speech_prob})"
        )
        stt_cls = SharedModelWhisperSTTService if telephony else WhisperSTTService
        return stt_cls(
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            settings=WhisperSTTService.Settings(
                model=settings.whisper_model,
                language=Language.EN,
                no_speech_prob=no_speech_prob,
            ),
        )

    logger.info("STT: Deepgram Nova-3")
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        audio_passthrough=False,
    )


def _seed_pooled_greeting_cache(
    svc: object,
    *,
    script: ScriptConfig,
    sample_rate: int,
) -> None:
    """Ensure opening greeting PCM is on the worker for instant play / greeting kick."""
    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE
    from .speech_renderer import prepare_for_speech, render_speech_telephony

    cache = getattr(svc, "_cache", None)
    if not isinstance(cache, dict):
        return
    try:
        from .inference_client import get_inference_client

        client = get_inference_client()
        telephony = sample_rate == TELEPHONY_PIPELINE_RATE
        greeting = prepare_for_speech(script.greeting)
        if not greeting.strip():
            return
        chunks = render_speech_telephony(
            greeting, max_words=settings.telephony_utterance_max_words
        )
        for chunk in chunks:
            line = chunk.text.strip()
            if not line or line in cache:
                continue
            cache[line] = client.synthesize_sync(
                line,
                sample_rate=sample_rate,
                telephony=telephony,
            )
        if cache:
            logger.info(f"Pooled greeting seeded: {len(chunks)} chunk(s) in worker cache")
    except Exception as exc:
        logger.warning(f"Pooled greeting seed failed (live synth on call): {exc}")


def _build_tts(*, script: ScriptConfig, sample_rate: int, telephony: bool = False):
    if _is_chatterbox_backend():
        from .chatterbox_paths import resolve_chatterbox_device, resolve_chatterbox_reference
        from .chatterbox_tts import ChatterboxTTSService, TELEPHONY_PIPELINE_RATE, warm_chatterbox_cache_sync

        telephony = telephony or sample_rate == TELEPHONY_PIPELINE_RATE
        if _inference_pool_enabled():
            from .inference_client import get_inference_client
            from .pooled_tts import PooledChatterboxTTSService

            client = get_inference_client()
            try:
                warm = client.warm_cache_sync(
                    texts=_script_cache_lines(script, telephony=telephony),
                    sample_rate=sample_rate,
                    telephony=telephony,
                )
                logger.info(
                    f"Pooled TTS cache warmed: {warm.get('cache_size', 0)} line(s) "
                    f"via {client._base}"
                )
            except Exception as exc:
                logger.warning(f"Pooled cache warm failed (live synthesis only): {exc}")
            svc = PooledChatterboxTTSService(sample_rate=sample_rate)
            _seed_pooled_greeting_cache(svc, script=script, sample_rate=sample_rate)
            return svc

        reference = resolve_chatterbox_reference(settings.chatterbox_reference_audio or None)
        device = resolve_chatterbox_device(
            settings.chatterbox_device or settings.whisper_device or None
        )
        logger.info(
            f"TTS: Chatterbox Turbo (device={device}, ref={reference.name}, telephony={telephony})"
        )
        try:
            cache = warm_chatterbox_cache_sync(
                texts=_script_cache_lines(script, telephony=telephony),
                reference_path=reference,
                device=device,
                exaggeration=settings.chatterbox_exaggeration,
                cfg_weight=settings.chatterbox_cfg_weight,
                sample_rate=sample_rate,
                telephony=telephony,
            )
        except Exception as exc:
            logger.warning(f"Chatterbox cache warm failed (live synthesis only): {exc}")
            cache = {}
        logger.info(f"Chatterbox cache warmed: {len(cache)} script line(s)")
        return ChatterboxTTSService(
            reference_audio=str(reference),
            device=device,
            exaggeration=settings.chatterbox_exaggeration,
            cfg_weight=settings.chatterbox_cfg_weight,
            sample_rate=sample_rate,
            cache=cache,
        )

    if _is_piper_backend():
        from .piper_tts import PiperTTSService, warm_piper_cache_sync

        logger.info("TTS: Piper (local)")
        cache = warm_piper_cache_sync(
            texts=_script_cache_lines(script, telephony=telephony),
            piper_exe=settings.piper_exe or None,
            model_path=settings.piper_model or None,
            speaker=settings.piper_speaker,
            sample_rate=sample_rate,
        )
        logger.info(f"Piper cache warmed: {len(cache)} script line(s)")
        return PiperTTSService(
            piper_exe=settings.piper_exe or None,
            model_path=settings.piper_model or None,
            speaker=settings.piper_speaker,
            sample_rate=sample_rate,
            cache=cache,
        )

    logger.info("TTS: Fish Audio")
    return FishAudioTTSService(
        api_key=settings.fish_api_key,
        model=settings.fish_model,
        reference_id=settings.fish_reference_id,
        sample_rate=sample_rate,
    )


_cached_stt = None
_cached_tts: dict[tuple[int, bool], object] = {}


def prewarm_voice_stack(
    script: ScriptConfig | None = None,
    *,
    sample_rate: int = 16000,
    telephony: bool = False,
) -> None:
    """Load STT/TTS weights before the first live call (avoids blocking on connect)."""
    global _cached_stt, _cached_tts
    _require_api_keys()
    script = script or ScriptConfig.load()
    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE

    if sample_rate == TELEPHONY_PIPELINE_RATE:
        telephony = True
    logger.info(
        f"Pre-warming voice stack (sample_rate={sample_rate}, telephony={telephony})..."
    )
    if _inference_pool_enabled():
        from .inference_client import get_inference_client

        client = get_inference_client()
        client.wait_until_ready()
        if _is_local_gpu_backend():
            _cached_stt = _build_stt(telephony=telephony)
        if _is_chatterbox_backend():
            _cached_tts[(sample_rate, telephony)] = _build_tts(
                script=script, sample_rate=sample_rate, telephony=telephony
            )
        logger.info("Voice stack pre-warm complete (inference pool mode).")
        return

    _cached_stt = _build_stt(telephony=telephony)
    _cached_tts[(sample_rate, telephony)] = _build_tts(
        script=script, sample_rate=sample_rate, telephony=telephony
    )
    logger.info("Voice stack pre-warm complete.")




def tts_processor_for_cleanup(pipeline) -> object | None:
    """Chatterbox TTS for cancel_background_work (not bulk-media/output processors)."""
    from .chatterbox_tts import ChatterboxTTSService
    from .pooled_tts import PooledChatterboxTTSService

    for proc in pipeline.processors:
        if isinstance(proc, (ChatterboxTTSService, PooledChatterboxTTSService)):
            return proc
    return None


def build_pipeline(
    transport,
    *,
    agent_user: str = "MIC-TEST",
    script: ScriptConfig | None = None,
    mic_test: bool = False,
    sample_rate: int = 16000,
    telephony: bool = False,
    vicidial_client: ViciDialClient | None = None,
    vicidial_call_id: str | None = None,
    transfer_preset: str | None = None,
    on_call_should_end: Callable[[str], Awaitable[None]] | None = None,
    is_call_active: Callable[[], bool] | None = None,
    telnyx_send_json: Callable[[str], Awaitable[None]] | None = None,
) -> Pipeline:
    """Assemble the live pipeline. `transport` provides audio in/out frames."""
    global _cached_stt

    if not PIPECAT_AVAILABLE:
        extra = "whisper" if _is_local_gpu_backend() else "deepgram"
        raise RuntimeError(
            f'Pipecat is not installed. Run: pip install "pipecat-ai[{extra},local,silero]" pyaudio'
        )

    _require_api_keys()

    from .chatterbox_tts import TELEPHONY_PIPELINE_RATE

    if sample_rate == TELEPHONY_PIPELINE_RATE:
        telephony = True

    script = script or ScriptConfig.load()
    if _is_chatterbox_backend():
        backend = "Chatterbox (Whisper + Chatterbox Turbo)"
    elif _is_piper_backend():
        backend = "GPU (Whisper + Piper)"
    else:
        backend = "managed (Deepgram + Fish)"
    mode = "telephony" if telephony else "local"
    logger.info(f"Voice backend: {backend} ({mode}, {sample_rate} Hz)")

    # Telephony: fresh STT processor each call (shared model weights). Reusing one
    # WhisperSTTService blocks StartFrame on call #2 when the prior call ended
    # during transcription.
    if telephony:
        stt = _build_stt(telephony=True)
        logger.info("STT: fresh Whisper processor for telephony (shared model weights)")
    else:
        stt = _cached_stt or _build_stt(telephony=False)
    tts_base = _cached_tts.get((sample_rate, telephony)) or _build_tts(
        script=script, sample_rate=sample_rate, telephony=telephony
    )
    # Each call gets its own TTS instance (shared warm cache) so GPU locks from a
    # prior call cannot block StartFrame on a Telnyx reconnect.
    if telephony and hasattr(tts_base, "clone_with_shared_cache"):
        tts = tts_base.clone_with_shared_cache()
    else:
        tts = tts_base
    vad = _build_vad(telephony=telephony)

    engine = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: answer_offscript(
            q, ctx, script.knowledge_base, telephony=telephony
        ),
    )
    call_controller = CallController()
    vici = None if mic_test else (vicidial_client or ViciDialClient())
    fronter = FronterProcessor(
        engine,
        vici,
        agent_user,
        mic_test=mic_test,
        call_controller=call_controller,
        telephony=telephony,
        telephony_phone_test=telephony and mic_test,
        vicidial_call_id=vicidial_call_id,
        transfer_preset=transfer_preset,
        on_call_should_end=on_call_should_end,
        is_call_active=is_call_active,
    )
    barge_in = BargeInProcessor(call_controller, telephony=telephony)
    max_words, pause_min, pause_max = _speech_settings(telephony=telephony)
    speech_renderer = SpeechRendererNode(
        call_controller,
        max_words=max_words,
        pause_min_ms=pause_min,
        pause_max_ms=pause_max,
        telephony=telephony and settings.telephony_single_utterance,
        telephony_max_words=settings.telephony_utterance_max_words,
    )

    processors = [
        transport.input(),
        vad,
        barge_in,
        stt,
        fronter,
        speech_renderer,
        tts,
    ]
    if telephony:
        from .telnyx_media import TelnyxBulkMediaProcessor, telephony_bulk_media_enabled

        if telephony_bulk_media_enabled():
            send_json = telnyx_send_json
            if send_json is None:
                ws_client = getattr(transport, "_client", None) or getattr(
                    transport, "_websocket", None
                )
                if ws_client is not None:

                    async def send_json(payload: str) -> None:  # type: ignore[misc]
                        if hasattr(ws_client, "send_text"):
                            await ws_client.send_text(payload)
                        else:
                            await ws_client.send(payload)

            if send_json is not None:
                encoding = os.getenv("TELNYX_STREAM_CODEC", "PCMU")
                processors.append(
                    TelnyxBulkMediaProcessor(send_json=send_json, encoding=encoding)
                )
                logger.info(f"Telnyx bulk media enabled (encoding={encoding})")
            else:
                logger.warning(
                    "Telnyx bulk media skipped — pass telnyx_send_json or fix transport WS"
                )
    processors.append(transport.output())

    return Pipeline(processors)
