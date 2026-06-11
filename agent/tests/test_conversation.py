from app.config import ScriptConfig
from app.conversation import Action, ConversationEngine, Intent, heuristic_classifier


def make_engine() -> ConversationEngine:
    script = ScriptConfig(
        greeting="Hi there.",
        pitch="We cut your power bill. Do you own your home?",
        qualifying_questions=["Do you own your home?", "Is your bill over 100 dollars?"],
    )
    return ConversationEngine(script=script)


def test_heuristic_classifier():
    assert heuristic_classifier("yes I do") == Intent.POSITIVE
    assert heuristic_classifier("not interested") == Intent.NEGATIVE
    assert heuristic_classifier("how much does it cost?") == Intent.QUESTION
    assert heuristic_classifier("") == Intent.UNCLEAR


def test_opens_with_greeting():
    e = make_engine()
    turn = e.open()
    assert turn.reply == "Hi there."
    assert turn.action == Action.SPEAK


def test_immediate_not_interested_hangs_up():
    e = make_engine()
    e.open()
    turn = e.handle("no, not interested")
    assert turn.action == Action.HANGUP


def test_qualified_lead_transfers():
    e = make_engine()
    e.open()
    e.handle("ok")                 # pitch delivered, enter QUALIFY
    e.handle("yes")                # answer q1 (positive)
    turn = e.handle("yes")         # answer q2 (positive) -> qualified
    assert turn.action == Action.TRANSFER


def test_unqualified_lead_ends():
    e = make_engine()
    e.open()
    e.handle("ok")                 # enter QUALIFY
    e.handle("hmm")                # q1, unclear
    turn = e.handle("hmm")         # q2, unclear -> not qualified
    assert turn.action == Action.HANGUP
