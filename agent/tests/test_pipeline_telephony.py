from app.config import ScriptConfig
from app.conversation import ConversationEngine
from app.models import KnowledgeEntry
from app.pipeline import should_telephony_barge_in


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


def test_coerce_yes_i_have_on_part_a():
    from app.config import ScriptConfig
    from app.conversation import ConversationEngine
    from app.pipeline import FronterProcessor

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits.",
        qualifying_questions=["Do you have Medicare Part A and Part B?", "How old are you?"],
    )
    engine = ConversationEngine(script=script)
    engine.open()
    engine.handle("ok")
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    assert proc._coerce_qualify_yes_stt("Yes, I have.") == "Yes"
    assert proc._coerce_qualify_yes_stt("Yes.") == "Yes."


def test_queue_coerces_yes_i_have_to_bare_yes():
    from app.config import ScriptConfig
    from app.conversation import ConversationEngine
    from app.pipeline import FronterProcessor
    from app.speech_renderer import CallState

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits.",
        qualifying_questions=["Do you have Medicare Part A and Part B?", "How old are you?"],
    )
    engine = ConversationEngine(script=script)
    engine.open()
    engine.handle("ok")
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._call.state = CallState.SPEAKING
    proc._queue_pending_caller_text("Yes.")
    proc._queue_pending_caller_text("Yes, I have.")
    assert len(proc._pending_caller_texts) == 1
    assert proc._pending_caller_texts[0].lower().rstrip(".!") == "yes"
    chosen = proc._collapse_caller_queue()
    assert chosen.lower().rstrip(".!") == "yes"


def test_collapse_prefers_bare_yes_over_yes_i_have():
    from app.pipeline import FronterProcessor

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._pending_caller_texts = ["Yes, I have.", "Yes."]
    chosen = proc._collapse_caller_queue()
    assert chosen.lower().rstrip(".!") == "yes"


def test_collapse_prefers_age_over_hello():
    from app.pipeline import FronterProcessor

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._pending_caller_texts = ["Yes.", "Hello?", "I am 85."]
    chosen = proc._collapse_caller_queue()
    assert "85" in chosen


def test_pending_early_ack_keeps_followup():
    from app.pipeline import FronterProcessor

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._followup_reply = "Do you have Medicare Part A and Part B?"
    proc._pending_caller_texts = ["Yes.", "Hello?"]
    assert proc._pending_is_early_ack_only()
    proc._pending_caller_texts = ["I am 85."]
    assert not proc._pending_is_early_ack_only()


def test_bare_yes_kept_after_part_a_ask():
    """Bare 'yes' after Part A must not be treated as discardable early-ack."""
    from app.config import ScriptConfig
    from app.conversation import ConversationEngine
    from app.pipeline import FronterProcessor

    script = ScriptConfig(
        greeting="Hi.",
        pitch=(
            "I'm calling because you qualify for some free Medicare benefits "
            "with your current Medicare plan."
        ),
        qualifying_questions=[
            "Do you have Medicare Part A and Part B?",
            "How old are you?",
        ],
    )
    engine = ConversationEngine(script=script)
    engine.open()
    engine.handle("I'm fine")  # joined pitch + Part A; qualify_idx=1
    assert engine._pitch_confirmed and engine._qualify_idx == 1
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._pending_caller_texts = ["Yes."]
    assert not proc._pending_is_early_ack_only()
    proc._pending_caller_texts = ["Yes, I have."]
    assert not proc._pending_is_early_ack_only()


def test_bare_yes_is_early_ack_on_age_ask():
    from app.config import ScriptConfig
    from app.conversation import ConversationEngine
    from app.pipeline import FronterProcessor

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits.",
        qualifying_questions=[
            "Do you have Medicare Part A and Part B?",
            "How old are you?",
            "Do you make your own decisions?",
        ],
    )
    engine = ConversationEngine(script=script)
    engine.open()
    engine.handle("ok")
    engine.handle("yes")  # Part A → age
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._pending_caller_texts = ["Yes."]
    assert proc._pending_is_early_ack_only()
    proc._pending_caller_texts = ["I am 72."]
    assert not proc._pending_is_early_ack_only()


def test_echo_drops_thank_you_and_you_can():
    from app.pipeline import (
        FronterProcessor,
        _is_likely_bot_echo,
        _is_meaningful_caller_text,
        _is_whisper_phantom,
    )

    assert _is_whisper_phantom("Thank you.")
    assert _is_whisper_phantom("Thank you. Thank you.")
    assert _is_whisper_phantom("You can.")
    pitch = (
        "I'm calling because you qualify for some free Medicare benefits "
        "with your current Medicare plan"
    )
    assert _is_likely_bot_echo("medicare benefits", pitch)
    assert _is_likely_bot_echo("you qualify", pitch)

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._engine._last_reply = pitch
    assert proc._should_drop_stt_as_echo("Thank you.")
    assert proc._should_drop_stt_as_echo("You can.")
    assert not proc._should_drop_stt_as_echo("I am fine.")
    assert not proc._should_drop_stt_as_echo("Yes.")
    assert _is_meaningful_caller_text("61")
    assert _is_meaningful_caller_text("92")
    assert not _is_meaningful_caller_text("hi")


def test_merge_age_fragments():
    from app.pipeline import FronterProcessor

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    assert proc._merge_transcripts("I am.", "61") == "I am 61"
    assert "92" in proc._merge_transcripts("I am", "92")
