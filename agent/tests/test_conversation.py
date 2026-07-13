from app.config import ScriptConfig
from app.conversation import Action, ConversationEngine, Intent, heuristic_classifier
from app.models import KnowledgeEntry


def make_engine() -> ConversationEngine:
    script = ScriptConfig(
        greeting="Hi there.",
        pitch="We cut your power bill. Do you own your home?",
        qualifying_questions=["Do you own your home?", "Is your bill over 100 dollars?"],
    )
    return ConversationEngine(script=script)


def test_heuristic_classifier():
    assert heuristic_classifier("yes I do") == Intent.POSITIVE
    assert heuristic_classifier("I'm fine") == Intent.POSITIVE
    assert heuristic_classifier("not interested") == Intent.NEGATIVE
    assert heuristic_classifier("how much does it cost?") == Intent.QUESTION
    assert heuristic_classifier("okay, what do you want?") == Intent.QUESTION
    assert heuristic_classifier("why are you calling me") == Intent.QUESTION
    assert heuristic_classifier("is this a scam") == Intent.QUESTION
    assert heuristic_classifier("") == Intent.UNCLEAR


def test_opens_with_greeting():
    e = make_engine()
    turn = e.open()
    assert turn.reply == "Hi there."
    assert turn.action == Action.SPEAK


def test_not_interested_soft_rebuttal_then_hangup():
    e = make_engine()
    e.open()
    turn = e.handle("not interested")
    assert turn.action == Action.SPEAK
    assert "eligibility" in turn.reply.lower()
    turn2 = e.handle("no stop calling")
    assert turn2.action == Action.HANGUP


def test_unclear_during_qualify_repeats_question():
    e = make_engine()
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("wow")
    assert turn.action == Action.SPEAK
    assert turn.reply == "Do you own your home?"


def test_qualified_lead_transfers():
    e = make_engine()
    e.open()
    e.handle("ok")                 # pitch delivered, enter QUALIFY
    e.handle("yes")                # ask q1
    e.handle("yes")                # ask q2
    turn = e.handle("yes")         # all qualifiers answered -> qualified
    assert turn.action == Action.TRANSFER


def test_unqualified_lead_ends():
    e = make_engine()
    e.open()
    e.handle("ok")
    e.handle("no")
    turn = e.handle("no, not interested")
    assert turn.action == Action.HANGUP


def test_kb_question_during_qualify_not_repeat():
    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Ready?",
        qualifying_questions=["Do you have Part A and B?", "Interested in plan review?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="How much does it cost",
                triggers=["how much", "cost", "price"],
                answer="The review is free.",
            ),
        ],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("how much does it cost")
    assert "free" in turn.reply.lower()
    assert turn.reply != "Do you have Part A and B?"


def test_third_kb_in_pitch_advances_to_pitch():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Ready?",
        qualifying_questions=["Do you have Part A and B?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="Who are you with",
                triggers=["who are you"],
                answer="Alex from ABC Benefits.",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("who are you")
    e.handle("who is calling")
    turn = e.handle("why are you calling me")
    assert "Medicare review" in turn.reply
