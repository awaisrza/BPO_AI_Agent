"""Knowledge-base matching + Gemini fallback for off-script caller questions."""

from __future__ import annotations

import re
from typing import Iterable

from loguru import logger

from .config import settings
from .gemini import TELEPHONY_KB_MISS_REPLY, generate_gemini_reply
from .models import KnowledgeEntry
from .speech_renderer import prepare_for_speech


_STOP_WORDS = frozenset(
    {"a", "an", "are", "be", "do", "for", "i", "is", "it", "me", "my", "on", "the", "to", "you", "your"}
)


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^\w\s']", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _entry_triggers(entry: KnowledgeEntry) -> list[str]:
    triggers: list[str] = []
    if entry.topic.strip():
        triggers.append(_normalize(entry.topic))
    for raw in entry.triggers:
        normalized = _normalize(raw)
        if normalized and normalized not in triggers:
            triggers.append(normalized)
    return triggers


def match_knowledge(utterance: str, entries: Iterable[KnowledgeEntry]) -> KnowledgeEntry | None:
    """Return the best KB entry for a caller utterance, or None."""
    normalized = _normalize(utterance)
    if not normalized:
        return None

    utter_words = set(normalized.split())
    best: KnowledgeEntry | None = None
    best_score = 0

    for entry in entries:
        if not entry.answer.strip():
            continue

        for trigger in _entry_triggers(entry):
            if len(trigger) < 3:
                continue

            score = 0
            if trigger in normalized or normalized in trigger:
                score = max(len(trigger), len(normalized)) * 2
            else:
                trigger_words = set(trigger.split())
                overlap = utter_words & trigger_words
                if not overlap:
                    continue
                distinctive = {w for w in overlap if w not in _STOP_WORDS and len(w) >= 3}
                # Require at least two *meaningful* overlapping words — a single
                # distinctive word plus filler like "a"/"is" is too weak a signal and
                # causes false hits on unrelated speech (e.g. "not a good time" vs.
                # "you're not a lot of comedy").
                if len(overlap) >= 2 and len(distinctive) >= 2:
                    score = len(distinctive) * 12 + len(overlap) * 4
                elif len(trigger_words) == 1:
                    word = next(iter(overlap))
                    if len(word) >= 4:
                        score = 10 + len(word)

            if score > best_score:
                best_score = score
                best = entry

    return best


def format_knowledge_prompt(entries: Iterable[KnowledgeEntry]) -> str:
    lines: list[str] = []
    for entry in entries:
        if not entry.answer.strip():
            continue
        label = entry.topic.strip() or "FAQ"
        triggers = ", ".join(entry.triggers) if entry.triggers else label
        lines.append(f"- {label} (when caller asks about: {triggers}) -> {entry.answer.strip()}")
    return "\n".join(lines)


def parse_knowledge_base(raw: object) -> list[KnowledgeEntry]:
    if not isinstance(raw, list):
        return []

    entries: list[KnowledgeEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        triggers = item.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [part.strip() for part in triggers.split(",") if part.strip()]
        elif isinstance(triggers, list):
            triggers = [str(part).strip() for part in triggers if str(part).strip()]
        else:
            triggers = []

        answer = str(item.get("answer", "")).strip()
        topic = str(item.get("topic", "")).strip()
        if not answer:
            continue

        entries.append(KnowledgeEntry(topic=topic, triggers=triggers, answer=answer))

    return entries


def _telephony_worth_gemini(question: str) -> bool:
    """Only call Gemini on PSTN for substantive questions — short asides must be instant."""
    words = [w for w in re.findall(r"[a-z0-9']+", question.lower()) if w]
    if len(words) < 5:
        return False
    # Clarifiers / asides while the bot is pitching — never wait on Gemini.
    joined = " ".join(words)
    skip_phrases = (
        "thats what",
        "what is that",
        "what was that",
        "say that again",
        "come again",
        "what is it about",
        "what is this about",
        "whats it about",
        "whats this about",
        "what is this call about",
        "yeah what is it about",
    )
    if joined in skip_phrases:
        return False
    if any(p in joined for p in ("what is it about", "what is this about", "why are you calling")):
        return False
    return True


def answer_offscript(
    question: str,
    context: str = "",
    entries: list[KnowledgeEntry] | None = None,
    *,
    telephony: bool = False,
) -> str:
    """KB first (exact approved answer), then Gemini grounded on KB, then safe fallback."""
    kb_entries = entries or []
    match = match_knowledge(question, kb_entries)
    if match:
        logger.info(f"Off-script KB hit: {match.topic or match.triggers}")
        return prepare_for_speech(match.answer)

    if telephony:
        # Prefer instant cached line over Gemini wait (3s+ silence kills PSTN calls).
        if not _telephony_worth_gemini(question):
            logger.info("Off-script short/unclear miss -> telephony fallback (no Gemini)")
            return ""
        if kb_entries and settings.google_api_key:
            logger.info("Off-script KB miss -> Gemini (telephony)")
            knowledge_text = format_knowledge_prompt(kb_entries)
            reply = prepare_for_speech(
                generate_gemini_reply(
                    question,
                    context,
                    knowledge_text,
                    timeout_secs=2.0,
                )
            )
            return reply or prepare_for_speech(TELEPHONY_KB_MISS_REPLY)
        logger.info("Off-script KB miss -> telephony fallback")
        return prepare_for_speech(TELEPHONY_KB_MISS_REPLY)

    if kb_entries:
        logger.info("Off-script KB miss -> Gemini")
        knowledge_text = format_knowledge_prompt(kb_entries)
        return prepare_for_speech(generate_gemini_reply(question, context, knowledge_text))

    logger.info("Off-script no KB -> Gemini defaults")
    return prepare_for_speech(generate_gemini_reply(question, context, ""))
