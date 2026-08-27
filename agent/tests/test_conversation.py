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
    assert "Medicare plan" in pitch_turn.reply
    follow = e.take_pending_followup()
    assert "eligibility check" in follow.lower()
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

def test_age_answer_advances_qualify():
    from app.conversation import _extract_age_years, _age_qualify_result

    assert _extract_age_years("I am 90 years old.") == 90
    assert _extract_age_years("I am 75.") == 75
    assert _extract_age_years("75") == 75
    assert _age_qualify_result("I am 75.") == "yes"
    assert _age_qualify_result("I am 40.") == "no"

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits. Do you have a moment?",
        qualifying_questions=["How old are you?", "Do you make your own decisions?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("ok")
    e.take_pending_followup()  # consent
    turn = e.handle("yes")  # -> Part A (auto-prepended for Medicare)
    assert "Part A" in turn.reply
    turn = e.handle("yes")  # Part A -> age
    assert turn.reply == "How old are you?"
    turn = e.handle("I am 75.")
    assert turn.reply == "Do you make your own decisions?"
    turn2 = e.handle("yes")
    assert turn2.action == Action.TRANSFER


def test_age_answer_not_hijacked_by_kb():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits. Do you have a moment?",
        qualifying_questions=["How old are you?", "Do you make your own decisions?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="Age confirm",
                triggers=["years old", "I am"],
                answer="Just to confirm you qualify - what age are you?",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    e.handle("ok")
    e.take_pending_followup()
    e.handle("yes")  # Part A
    turn = e.handle("yes")  # -> age
    assert turn.reply == "How old are you?"
    turn = e.handle("I am 90 years old.")
    assert "confirm you qualify" not in turn.reply.lower()
    assert turn.reply == "Do you make your own decisions?"


def test_pitch_queues_medicare_consent_followup():
    script = ScriptConfig(
        greeting="Hi, how are you?",
        pitch=(
            "I'm calling because you qualify for some free Medicare benefits "
            "with your current Medicare plan. Do you have Medicare Part A and Part B?"
        ),
        qualifying_questions=["How old are you?", "Do you make your own decisions?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    turn = e.handle("I am good")
    assert "Part A" not in turn.reply
    assert "qualify" in turn.reply.lower()
    follow = e.take_pending_followup()
    assert "Part A" in follow
    assert follow.strip().endswith("?")
    turn2 = e.handle("Yes.")
    assert "old" in turn2.reply.lower()


def test_pitch_then_part_a_then_age_order():
    script = ScriptConfig(
        greeting="Hi, how are you?",
        pitch=(
            "I'm calling because you qualify for some free Medicare benefits "
            "with your current Medicare plan."
        ),
        qualifying_questions=[
            "Do you have Medicare Part A and Part B?",
            "How old are you?",
            "Do you make your own decisions?",
        ],
    )
    e = ConversationEngine(script=script)
    e.open()
    turn = e.handle("I'm fine")
    assert "Part A" not in turn.reply
    assert e.take_pending_followup() == "Do you have Medicare Part A and Part B?"
    turn = e.handle("Yes")
    assert turn.reply == "How old are you?"
    turn = e.handle("I am 82.")
    assert turn.reply == "Do you make your own decisions?"


def test_medicare_prepends_part_a_when_script_starts_at_age():
    script = ScriptConfig(
        greeting="Hi.",
        pitch=(
            "I'm calling because you qualify for some free Medicare benefits "
            "with your current Medicare plan."
        ),
        qualifying_questions=["How old are you?", "Do you make your own decisions?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("I'm fine")
    assert "Part A" in e.take_pending_followup()
    turn = e.handle("Yes")
    assert "old" in turn.reply.lower()


def test_schedule_kb_ignored_during_pitch():
    from app.knowledge import answer_offscript as kb_answer

    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare benefits. Do you have a moment?",
        qualifying_questions=["Do you have Medicare Part A and Part B?"],
        knowledge_base=[
            KnowledgeEntry(
                topic="Call me back later",
                triggers=["call me back", "busy", "later", "book", "right now"],
                answer="Sure — what time works best for you tomorrow?",
            ),
        ],
    )
    e = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: kb_answer(q, ctx, script.knowledge_base),
    )
    e.open()
    turn = e.handle("come on a book right now")
    assert "tomorrow" not in turn.reply.lower()
    assert "medicare" in turn.reply.lower() or "moment" in turn.reply.lower() or "qualify" in turn.reply.lower()


def test_okay_does_not_skip_age_question():
    script = ScriptConfig(
        greeting="Hi.",
        pitch="Medicare. Ready?",
        qualifying_questions=["How old are you?", "Do you make your own decisions?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("ok")
    e.handle("yes")
    turn = e.handle("Oh, okay.")
    assert "old" in turn.reply.lower() or "age" in turn.reply.lower()
    assert turn.reply != "Do you make your own decisions?"


def test_soft_no_requeues_consent_followup():
    script = ScriptConfig(
        greeting="Hi, how are you?",
        pitch=(
            "I'm calling because you qualify for some free Medicare benefits "
            "with your current Medicare plan. Do you have Medicare Part A and Part B?"
        ),
        qualifying_questions=["How old are you?"],
    )
    e = ConversationEngine(script=script)
    e.open()
    e.handle("I'm fine")
    e.take_pending_followup()  # Part A already queued as current Q
    turn = e.handle("No.")
    assert "eligibility" in turn.reply.lower() or "thirty" in turn.reply.lower()
    follow = e.take_pending_followup()
    assert "Part A" in follow
