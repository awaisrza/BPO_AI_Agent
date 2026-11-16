from app.speech_renderer import prepare_for_speech
from app.telnyx_media import greeting_pcm_from_cache


class _FakeTts:
    def __init__(self, cache: dict[str, bytes]) -> None:
        self._cache = cache


def test_greeting_pcm_from_cache_single_chunk():
    greeting = "Hey, this is Alex calling from Healthcare Benefits. How are you doing today?"
    pcm = b"\x01\x02"
    tts = _FakeTts({prepare_for_speech(greeting): pcm})
    out = greeting_pcm_from_cache(
        tts,
        greeting,
        script_greeting=greeting,
        greeting_single_chunk=True,
    )
    assert out == pcm


def test_greeting_pcm_from_cache_joins_telephony_chunks():
    tts = _FakeTts({"First sentence.": b"a", "Second sentence.": b"b"})
    out = greeting_pcm_from_cache(
        tts,
        "First sentence. Second sentence.",
        telephony_max_words=40,
    )
    assert out == b"ab"
