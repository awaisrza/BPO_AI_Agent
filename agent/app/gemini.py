"""Gemini helper for off-script caller questions."""

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


def answer_offscript(question: str, context: str = "", knowledge: str = DEFAULT_KNOWLEDGE) -> str:
    """Return a short spoken reply for an unexpected caller question."""
    if not settings.google_api_key:
        return "That's a great question — let me connect you with a specialist who can help."

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed; using fallback off-script reply")
        return "Let me connect you with a specialist who can answer that."

    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    prompt = f"""You are a friendly outbound fronter on a live US phone call.
Reply in ONE short sentence (max 20 words). Sound natural, not salesy.
Only use facts from the knowledge base. If unsure, offer to connect a specialist.

CURRENT SCRIPT STEP: {context}

KNOWLEDGE:
{knowledge.strip()}

CALLER SAID: {question}

YOUR REPLY:"""

    try:
        response = model.generate_content(prompt)
        reply = (response.text or "").strip()
        return reply or "Let me connect you with a specialist who can answer that."
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Gemini off-script error: {exc}")
        return "Let me connect you with a specialist who can answer that."
