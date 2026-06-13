"""Knowledge-base matching + Gemini fallback for off-script caller questions."""

from __future__ import annotations

import re
from typing import Iterable

from loguru import logger

from .gemini import generate_gemini_reply
from .models import KnowledgeEntry


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
                score = max(len(trigger), len(normalized))
            else:
                trigger_words = set(trigger.split())
                overlap = utter_words & trigger_words
                if not overlap:
                    continue
                if len(overlap) >= 2:
                    score = len(overlap) * 10
                elif len(trigger_words) == 1 and len(next(iter(overlap))) >= 4:
                    score = 8

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


def answer_offscript(
    question: str,
    context: str = "",
    entries: list[KnowledgeEntry] | None = None,
) -> str:
    """KB first (exact approved answer), then Gemini grounded on KB, then safe fallback."""
    kb_entries = entries or []
    match = match_knowledge(question, kb_entries)
    if match:
        logger.info(f"Off-script KB hit: {match.topic or match.triggers}")
        return match.answer

    if kb_entries:
        logger.info("Off-script KB miss -> Gemini")
        knowledge_text = format_knowledge_prompt(kb_entries)
        return generate_gemini_reply(question, context, knowledge_text)

    logger.info("Off-script no KB -> Gemini defaults")
    return generate_gemini_reply(question, context, "")
