"""Gemini helper for off-script caller questions (used after KB lookup misses)."""

from __future__ import annotations

from loguru import logger

from .config import settings

DEFAULT_KNOWLEDGE = """
who_is_this: Sarah from ABC Benefits, a licensed Medicare benefits provider.
is_this_a_scam: This is a legitimate call. It may be recorded for quality assurance.
how_much: The licensed specialist can go over exact numbers after I connect you.
not_interested: Understood. I will remove your number. Have a great day.
call_me_back: Sure — what time works best for you tomorrow?
"""

FALLBACK_REPLY = "Let me connect you with a specialist who can answer that."

# Spoken on live PSTN when KB misses — must stay short and pre-cacheable (no Gemini wait).
TELEPHONY_KB_MISS_REPLY = (
    "I'm not sure on that one — a licensed specialist can help. "
    "Can we finish this quick eligibility check first?"
)

GEMINI_TIMEOUT_SECS = 4.0


def generate_gemini_reply(
    question: str,
    context: str = "",
    knowledge: str = "",
    *,
    timeout_secs: float = GEMINI_TIMEOUT_SECS,
) -> str:
    """Return a short spoken reply using Gemini, grounded on the campaign knowledge base."""
    if not settings.google_api_key:
        return FALLBACK_REPLY

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed; using fallback off-script reply")
        return FALLBACK_REPLY

    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    knowledge_block = (knowledge or DEFAULT_KNOWLEDGE).strip()
    prompt = f"""You are Sarah, a calm US Medicare outbound fronter on a live phone call.

Reply rules (strict):
- Spoken conversation only — never written or formal tone
- ONE short sentence per idea (max 14 words)
- Soft, helpful tone — not pushy or salesy
- Qualify gently; clarity over completeness
- Use ONLY facts from the knowledge base below
- Do NOT invent prices, guarantees, or plan details
- If KB does not cover it, offer a licensed specialist on transfer

Objection handling (stay brief):
- "Not interested" -> acknowledge, one soft question or polite exit
- "Is this a scam?" -> reassure with legitimacy, no defensiveness
- "How much?" -> specialist explains after quick qualification
- "Call me back" -> ask for a good time, one sentence

CURRENT SCRIPT STEP: {context}

KNOWLEDGE BASE:
{knowledge_block}

CALLER SAID: {question}

YOUR SPOKEN REPLY (one or two short sentences max):"""

    def _call() -> str:
        response = model.generate_content(prompt)
        reply = (response.text or "").strip()
        if reply:
            from .speech_renderer import prepare_for_speech

            reply = prepare_for_speech(reply)
        return reply or FALLBACK_REPLY

    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call)
            return future.result(timeout=timeout_secs)
    except FuturesTimeout:
        logger.warning(f"Gemini timed out after {timeout_secs}s — using fallback")
        return FALLBACK_REPLY
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Gemini off-script error: {exc}")
        return FALLBACK_REPLY
