from app.speech_renderer import (
    CallController,
    CallState,
    normalize_spoken_text,
    prepare_for_speech,
    render_speech,
    render_speech_telephony,
    split_spoken_sentences,
)


def test_normalize_contractions():
    text = normalize_spoken_text("I am calling to verify your Medicare eligibility.")
    assert "I'm calling about your Medicare plan" in text


def test_prepare_for_speech_medicare_tone():
    text = prepare_for_speech("Please be advised that I am calling regarding your Medicare plan.")
    assert "just so you know" in text.lower()
    assert "i'm calling about" in text.lower()


def test_call_controller_finish_playback_opens_turn():
    ctrl = CallController()
    ctrl.begin_bot_reply(2)
    ctrl.finish_bot_playback()
    assert ctrl.can_accept_caller()


def test_call_controller_turn_gating():
    ctrl = CallController()
    ctrl.begin_bot_reply(2)
    assert ctrl.state == CallState.SPEAKING
    assert not ctrl.can_accept_caller()
    ctrl.on_bot_chunk_finished()
    assert not ctrl.can_accept_caller()
    ctrl.on_bot_chunk_finished()
    assert ctrl.can_accept_caller()
    ctrl.close_user_turn()
    assert not ctrl.can_accept_caller()


def test_split_long_sentence():
    long = (
        "I am calling to verify your Medicare eligibility and assist you in understanding "
        "your current plan options for the upcoming enrollment period."
    )
    parts = split_spoken_sentences(long, max_words=14)
    assert len(parts) >= 2
    assert all(len(p.split()) <= 14 for p in parts)


def test_render_speech_adds_pauses():
    chunks = render_speech("Hi, this is Sarah. Do you have a moment?")
    assert len(chunks) >= 2
    assert chunks[0].pause_after_ms >= 400
    assert chunks[-1].pause_after_ms == 0


def test_render_speech_no_paragraph_chunks():
    chunks = render_speech(
        "I am calling about Medicare. Would you be able to answer two quick questions today?"
    )
    assert chunks
    assert all(len(c.text.split()) <= 14 for c in chunks)


def test_render_speech_telephony_lead_sentence_first():
    greeting = (
        "Hi, this is Alex calling on a recorded line. "
        "How are you today? I'm calling about your Medicare plan."
    )
    chunks = render_speech_telephony(greeting)
    assert len(chunks) >= 2
    assert chunks[0].pause_after_ms == 0
    assert "Hi" in chunks[0].text
    assert all(c.pause_after_ms == 0 for c in chunks)


def test_render_speech_telephony_single_sentence():
    chunks = render_speech_telephony("Thanks for your time.")
    assert len(chunks) == 1


def test_render_speech_telephony_no_micro_pauses():
    chunks = render_speech("Hi. How are you? Great.", pause_min_ms=400, pause_max_ms=700)
    assert any(c.pause_after_ms > 0 for c in chunks)
    phone = render_speech_telephony("Hi. How are you? Great.")
    assert all(c.pause_after_ms == 0 for c in phone)


def test_written_to_spoken_rewrite():
    chunks = render_speech("Would you be able to assist me in order to review benefits?")
    joined = " ".join(c.text for c in chunks).lower()
    assert "can you" in joined
    assert "in order to" not in joined


def test_script_cache_covers_kb_anchor_chunks():
    from app.config import ScriptConfig
    from app.conversation import ConversationEngine
    from app.knowledge import answer_offscript
    from app.pipeline import _script_cache_lines

    script = ScriptConfig.load("scripts/campaigns/4c3aaed2-2dc6-4828-9d19-1024636dc0ac.json")
    engine = ConversationEngine(
        script=script,
        answer_offscript=lambda q, ctx: answer_offscript(
            q, ctx, script.knowledge_base, telephony=True
        ),
    )
    engine.open()
    engine.handle("I'm good")
    turn = engine.handle("how did you get my number")
    cache = set(_script_cache_lines(script, telephony=True))
    for chunk in render_speech_telephony(turn.reply):
        assert chunk.text.strip() in cache, chunk.text
    follow = engine.take_pending_followup()
    assert follow
    for chunk in render_speech_telephony(follow):
        assert chunk.text.strip() in cache, chunk.text
