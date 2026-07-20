import asyncio
import time

from app.config import ScriptConfig
from app.conversation import ConversationEngine
from app.models import KnowledgeEntry
from app.pipeline import FronterProcessor, _is_meaningful_caller_text, should_telephony_barge_in


def _medicare_engine() -> ConversationEngine:
    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="How did you get my number",
                triggers=["how did you get my number"],
                answer="Your number came from a public Medicare outreach list.",
            ),
            KnowledgeEntry(
                topic="Already have benefits",
                triggers=["already have"],
                answer="That's great — a lot of folks still qualify for extra savings.",
            ),
        ],
    )
    return ConversationEngine(script=script)


def test_barge_in_for_kb_question():
    engine = _medicare_engine()
    assert should_telephony_barge_in("How did you get my number?", engine)


def test_barge_in_for_kb_objection_without_question_mark():
    engine = _medicare_engine()
    assert should_telephony_barge_in("I already have benefits.", engine)


def test_no_barge_in_for_short_yes():
    engine = _medicare_engine()
    assert not should_telephony_barge_in("Yeah.", engine)


def test_no_barge_in_for_thank_you():
    engine = _medicare_engine()
    assert not should_telephony_barge_in("Thank you.", engine)


def _make_fronter(*, engine=None, telephony: bool = True) -> FronterProcessor:
    engine = engine or _medicare_engine()
    return FronterProcessor(
        engine,
        vicidial=None,
        agent_user="TEST",
        mic_test=True,
        telephony=telephony,
        telephony_phone_test=telephony,
    )


def test_collapse_caller_queue_merges_instead_of_discarding():
    """Two utterances queued while the bot was busy must both survive — the old
    behavior picked one 'winning' utterance by priority and silently dropped the
    other, which is how a caller's actual answer could get lost."""
    fronter = _make_fronter()
    fronter._pending_caller_texts = ["Yes I am", "I turned 66 last year"]
    merged = fronter._collapse_caller_queue()
    assert merged is not None
    assert "yes i am" in merged.lower()
    assert "66" in merged or "last year" in merged.lower()
    assert fronter._pending_caller_texts == []


def test_collapse_caller_queue_dedupes_overlapping_fragments():
    fronter = _make_fronter()
    fronter._pending_caller_texts = ["I have Part A", "I have Part A and Part B"]
    merged = fronter._collapse_caller_queue()
    assert merged == "I have Part A and Part B"


def test_greeting_ack_runs_fsm_on_event_loop():
    """Greeting acks must not wait on the shared TTS thread pool — that was the
    'CALLER: I am good.' → silence → remote hangup failure mode."""
    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?"],
    )
    engine = ConversationEngine(script=script)
    engine.open()
    fronter = _make_fronter(engine=engine)

    assert not fronter._engine_may_block("I am good.")

    async def _run() -> None:
        await fronter._handle_caller("I am good.")

    asyncio.run(_run())
    assert "medicare" in fronter._engine.script.pitch.lower()
    assert fronter._engine.state.value == "qualify"


def test_handle_caller_does_not_block_event_loop():
    """engine.handle() (which can call Gemini synchronously) must run off the
    event loop — otherwise a single off-script question freezes the entire
    pipeline (no keepalive, no other frames) for the duration of the call."""
    slow_calls: list[float] = []

    def slow_offscript(question: str, ctx: str) -> str:
        slow_calls.append(time.monotonic())
        time.sleep(0.3)  # simulate a blocking Gemini HTTP call
        return "Here's a slow answer with enough words to count as substantive."

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?"],
    )
    engine = ConversationEngine(script=script, answer_offscript=slow_offscript)
    engine.open()
    engine.handle("ok")  # enter QUALIFY pre-consent so an off-script question is used
    fronter = _make_fronter(engine=engine)

    ticks: list[float] = []

    async def _tick_counter() -> None:
        for _ in range(20):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.02)

    async def _run() -> None:
        await asyncio.gather(
            fronter._handle_caller("what is your deductible amount please tell me"),
            _tick_counter(),
        )

    asyncio.run(_run())

    # If engine.handle() had blocked the loop, the tick counter could not have
    # advanced *during* the 0.3s sleep — its ticks would all land after it.
    assert slow_calls, "offscript callback was never invoked"
    blocking_call_time = slow_calls[0]
    ticks_during_block = [t for t in ticks if abs(t - blocking_call_time) < 0.3]
    assert len(ticks_during_block) >= 3, (
        "event loop appears to have been blocked during the slow off-script call"
    )


def test_hangup_defers_termination_until_bot_finishes_speaking():
    """FSM HANGUP on a telephony call must not fire the end-call callback until
    the closing line has actually finished playing."""
    ended: list[str] = []

    async def _on_call_should_end(reason: str) -> None:
        ended.append(reason)

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=[],
        not_interested_line="No problem, have a great day.",
    )
    engine = ConversationEngine(script=script)
    engine.open()
    fronter = FronterProcessor(
        engine,
        vicidial=None,
        agent_user="TEST",
        mic_test=True,
        telephony=True,
        telephony_phone_test=True,
        on_call_should_end=_on_call_should_end,
    )

    async def _run() -> None:
        await fronter._handle_caller("no, not interested")
        await fronter._handle_caller("no, please stop calling")

    asyncio.run(_run())

    # The callback must not have fired yet — only once BotStoppedSpeakingFrame
    # for the closing line is observed (simulated directly here).
    assert ended == []
    assert fronter._pending_terminal_action == "hangup"


def test_stt_click_fragment_is_ignored():
    assert not _is_meaningful_caller_text("Click")
    assert not _is_meaningful_caller_text("click.")
