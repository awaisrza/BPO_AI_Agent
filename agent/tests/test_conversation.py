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
    assert heuristic_classifier("no") == Intent.NEGATIVE
    assert heuristic_classifier("not") == Intent.UNCLEAR
    assert heuristic_classifier("nothing") == Intent.UNCLEAR
    assert heuristic_classifier("know") == Intent.UNCLEAR
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
    from app.knowledge import answer_offscript as kb_answer

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
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("how much does it cost")
    assert "free" in turn.reply.lower()
    assert turn.reply != "Do you have Part A and B?"


def test_thank_you_before_consent_advances_to_qualify():
    script = ScriptConfig(
        greeting="Hi.",
        pitch=(
            "Great — I'll be quick. I'm calling about your Medicare plan. "
            "Do you have a moment for a quick eligibility check?"
        ),
        qualifying_questions=["Do you have Part A and B?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("I'm good")
    turn = e.handle("thank you")
    assert "Part A" in turn.reply
    assert "eligibility check" not in turn.reply.lower()


def test_thank_you_during_pitch_playback_does_not_repeat_consent():
    """Simulates caller saying thank you while bot is still playing the pitch."""
    script = ScriptConfig(
        greeting="Hi.",
        pitch=(
            "Great — I'll be quick. I'm calling about your Medicare plan. "
            "Do you have a moment for a quick eligibility check?"
        ),
        qualifying_questions=["Do you have Part A and B?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    pitch_turn = e.handle("I'm good")
    assert "eligibility check" in pitch_turn.reply.lower()
    turn = e.handle("thank you")
    assert "Part A" in turn.reply
    assert turn.reply != "Do you have a moment for a quick eligibility check?"


def test_unclear_after_pitch_uses_short_prompt_not_repeat():
    script = ScriptConfig(
        greeting="Hi.",
        pitch=(
            "Great — I'll be quick. I'm calling about your Medicare plan. "
            "Do you have a moment for a quick eligibility check?"
        ),
        qualifying_questions=["Do you have Part A and B?"],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: "",
    )
    e.open()
    e.handle("I'm good")
    turn = e.handle("huh")
    assert "yes or no" in turn.reply.lower()
    assert "eligibility check" not in turn.reply.lower()


def test_offscript_miss_escalates_not_repeat():
    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?"],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: "",
    )
    e.open()
    e.handle("I'm good")
    t1 = e.handle("what is the weather")
    t2 = e.handle("tell me a joke")
    # Pitch already asked consent — escalate skips the verbatim repeat.
    assert "yes or no" in t1.reply.lower()
    assert t1.reply == t2.reply


def test_greeting_ack_does_not_advance_qualify():
    e = make_engine()
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("I'm fine")
    assert turn.reply == "Do you own your home?"


def test_loose_positive_does_not_skip_qualifiers():
    e = make_engine()
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("good")
    assert turn.reply == "Do you own your home?"
    assert "100 dollars" not in turn.reply


def test_all_right_during_qualify_advances():
    e = make_engine()
    e.open()
    e.handle("ok")
    e.handle("yes")
    e.handle("how did you get my number")
    turn = e.handle("all right")
    assert "100 dollars" in turn.reply or "bill" in turn.reply.lower()


def test_soft_ack_during_consent_advances():
    e = make_engine()
    e.open()
    e.handle("ok")
    turn = e.handle("I think that's good")
    assert turn.reply == "Do you own your home?"


def test_unclear_question_during_pitch_delivers_pitch():
    e = make_engine()
    e.open()
    turn = e.handle("That's what?")
    assert "power bill" in turn.reply.lower() or "own your home" in turn.reply.lower()


def test_kb_already_have_reanchors_qualify_question():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=[
            "Do you have Part A and B?",
            "Are you interested in reviewing your plan options this year?",
        ],
        knowledge_base=[
            KnowledgeEntry(
                topic="Already have benefits",
                triggers=["already have"],
                answer="That's great — a lot of folks still qualify for extra savings.",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("ok")
    e.handle("yes")
    e.handle("yes")
    turn = e.handle("I already have benefits")
    assert "great" in turn.reply.lower()
    assert "plan options" not in turn.reply.lower()
    assert "plan options" in e.take_pending_followup().lower()


def test_all_right_after_kb_advances_to_qualify():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="How did you get my number",
                triggers=["how did you get"],
                answer="Your number came from a public Medicare outreach list.",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("ok")
    e.handle("how did you get my name")
    turn = e.handle("all right")
    assert "Part A" in turn.reply
    assert "eligibility check" not in turn.reply.lower()


def test_kb_how_did_you_get_number_reanchors_pitch_consent():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Great — I'll be quick. I'm calling about your Medicare plan. Do you have a moment for a quick eligibility check?",
        qualifying_questions=["Do you have Part A and B?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="How did you get my number",
                triggers=["how did you get my number"],
                answer="Your number came from a public Medicare outreach list.",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("I'm good")
    turn = e.handle("how did you get my number")
    assert "outreach list" in turn.reply.lower()
    assert "eligibility check" not in turn.reply.lower()
    follow = e.take_pending_followup()
    assert "moment" in follow.lower() or "eligibility" in follow.lower()


def test_kb_already_have_benefits_during_qualify():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare review. Do you have a moment?",
        qualifying_questions=["Do you have Part A and B?", "Interested in plan review?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="Already have benefits",
                triggers=["already have", "already on medicare"],
                answer="That's great — a lot of folks still qualify for extra savings.",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("ok")
    e.handle("yes")
    e.handle("yes")
    turn = e.handle("I already have benefits")
    assert "great" in turn.reply.lower() or "savings" in turn.reply.lower()
    assert "plan review" not in turn.reply.lower()
    assert "plan review" in e.take_pending_followup().lower()


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
