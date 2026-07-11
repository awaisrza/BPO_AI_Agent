from app.speech_renderer import (
    CallController,
    CallState,
    normalize_spoken_text,
    prepare_for_speech,
    render_speech,
    split_spoken_sentences,
)


def test_normalize_contractions():
    text = normalize_spoken_text("I am calling to verify your Medicare eligibility.")
    assert "I'm calling about your Medicare plan" in text


def test_prepare_for_speech_medicare_tone():
    text = prepare_for_speech("Please be advised that I am calling regarding your Medicare plan.")
    assert "just so you know" in text.lower()
    assert "i'm calling about" in text.lower()


def test_call_controller_barge_in_states():
    ctrl = CallController()
    ctrl.on_response_start()
    assert ctrl.state == CallState.SPEAKING
    assert ctrl.should_interrupt()
    ctrl.on_interruption()
    assert ctrl.state == CallState.LISTENING
    assert ctrl.interrupted
    ctrl.on_listening()
    assert not ctrl.interrupted


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


def test_written_to_spoken_rewrite():
    chunks = render_speech("Would you be able to assist me in order to review benefits?")
    joined = " ".join(c.text for c in chunks).lower()
    assert "can you" in joined
    assert "in order to" not in joined
