from app.models import KnowledgeEntry
from app.knowledge import answer_offscript, match_knowledge, parse_knowledge_base


def _entries() -> list[KnowledgeEntry]:
    return [
        KnowledgeEntry(
            topic="Who is calling?",
            triggers=["who is this", "who are you", "spam"],
            answer="This is Sarah from ABC Benefits on a recorded line.",
        ),
        KnowledgeEntry(
            topic="How much?",
            triggers=["how much", "cost", "price"],
            answer="The specialist can go over exact numbers after I connect you.",
        ),
    ]


def test_match_knowledge_finds_trigger_phrase():
    hit = match_knowledge("who are you calling from?", _entries())
    assert hit is not None
    assert hit.topic == "Who is calling?"


def test_match_knowledge_finds_cost_question():
    hit = match_knowledge("yeah but what's the catch, how much is it?", _entries())
    assert hit is not None
    assert hit.topic == "How much?"


def test_match_knowledge_does_not_confuse_why_calling_with_who_are_you():
    entries = [
        KnowledgeEntry(
            topic="Who are you with",
            triggers=["who are you", "who are you with"],
            answer="Alex from ABC Benefits.",
        ),
        KnowledgeEntry(
            topic="Who is calling",
            triggers=["who is calling", "why are you calling"],
            answer="Medicare eligibility outreach.",
        ),
    ]
    hit = match_knowledge("why are you calling me", entries)
    assert hit is not None
    assert hit.topic == "Who is calling"


def test_match_knowledge_returns_none_when_no_hit():
    assert match_knowledge("my dog is barking", _entries()) is None


def test_match_knowledge_rejects_weak_stopword_overlap():
    """Two words overlapping where only one is meaningful (the other is filler
    like "a"/"is"/"me") must not trigger a KB answer — this caused the bot to
    answer "You're not a lot of comedy" with a random "call me back" reply."""
    entries = [
        KnowledgeEntry(
            topic="Call me back later",
            triggers=["call me back", "not a good time", "busy", "later"],
            answer="Sure — what time works best for you tomorrow?",
        ),
    ]
    assert match_knowledge("You're not a lot of comedy.", entries) is None
    assert match_knowledge("We're just not an American.", entries) is None


def test_match_knowledge_still_matches_two_real_words():
    entries = [
        KnowledgeEntry(
            topic="Already have benefits",
            triggers=["already on medicare"],
            answer="Still worth a quick check.",
        ),
    ]
    hit = match_knowledge("I'm already on my medicare plan", entries)
    assert hit is not None
    assert hit.topic == "Already have benefits"


def test_parse_knowledge_base_from_dashboard_shape():
    raw = [
        {
            "topic": "Who is calling?",
            "triggers": ["who are you", "spam"],
            "answer": "Sarah from ABC Benefits.",
        }
    ]
    entries = parse_knowledge_base(raw)
    assert len(entries) == 1
    assert entries[0].triggers == ["who are you", "spam"]


def test_answer_offscript_uses_kb_before_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.knowledge.generate_gemini_reply",
        lambda *_args, **_kwargs: "GEMINI SHOULD NOT RUN",
    )
    reply = answer_offscript("who is this?", "pitch", _entries())
    assert reply == "This is Sarah from ABC Benefits on a recorded line."


def test_answer_offscript_falls_back_to_gemini_on_miss(monkeypatch):
    monkeypatch.setattr(
        "app.knowledge.generate_gemini_reply",
        lambda q, ctx, kb: f"gemini:{q}",
    )
    reply = answer_offscript("my wife handles the bills", "qualify", _entries())
    assert reply == "gemini:my wife handles the bills"


def test_answer_offscript_telephony_short_miss_skips_gemini(monkeypatch):
    monkeypatch.setattr("app.knowledge.settings.google_api_key", "test-key")
    monkeypatch.setattr(
        "app.knowledge.generate_gemini_reply",
        lambda *_args, **_kwargs: "GEMINI SHOULD NOT RUN",
    )
    reply = answer_offscript("That's what?", "pitch", _entries(), telephony=True)
    assert reply == ""


def test_answer_offscript_telephony_returns_fallback_on_miss(monkeypatch):
    monkeypatch.setattr("app.knowledge.settings.google_api_key", "")
    reply = answer_offscript(
        "can you explain what medicare plan options mean today",
        "pitch",
        _entries(),
        telephony=True,
    )
    assert "specialist" in reply.lower()


def test_answer_offscript_telephony_uses_gemini_on_miss(monkeypatch):
    monkeypatch.setattr("app.knowledge.settings.google_api_key", "test-key")
    monkeypatch.setattr(
        "app.knowledge.generate_gemini_reply",
        lambda q, ctx, kb, timeout_secs=2.0: f"gemini:{q}",
    )
    question = "can you explain what medicare plan options mean today"
    reply = answer_offscript(question, "pitch", _entries(), telephony=True)
    assert reply == f"gemini:{question}"
