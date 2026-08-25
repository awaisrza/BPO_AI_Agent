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


def test_collapse_prefers_yes_over_what():
    from app.pipeline import FronterProcessor

    engine = _medicare_engine()
    proc = FronterProcessor(engine, None, "6666", telephony=True)
    proc._pending_caller_texts = ["Yes.", "What?", "Yeah."]
    chosen = proc._collapse_caller_queue()
    assert chosen.lower().rstrip(".!") in {"yes", "yeah"}
    assert proc._pending_caller_texts == []
