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


def generate_gemini_reply(question: str, context: str = "", knowledge: str = "") -> str:
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
- Spoken conversation only — never written/formal tone
- ONE short sentence per idea (max 14 words)
- Soft, helpful tone — not pushy or salesy
- Qualify gently; clarity over completeness
- Use ONLY facts from the knowledge base below
- Do NOT invent prices, guarantees, or offers
- If KB does not cover it, say a licensed specialist can explain on transfer

CURRENT SCRIPT STEP: {context}

KNOWLEDGE BASE:
{knowledge_block}

CALLER SAID: {question}

YOUR SPOKEN REPLY (one or two short sentences max):"""

    try:
        response = model.generate_content(prompt)
        reply = (response.text or "").strip()
        if reply:
            from .speech_renderer import normalize_spoken_text

            reply = normalize_spoken_text(reply)
        return reply or FALLBACK_REPLY
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Gemini off-script error: {exc}")
        return FALLBACK_REPLY
