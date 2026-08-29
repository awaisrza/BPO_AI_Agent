"""Pure conversation state machine for the fronter.

Deterministic flow (greet -> pitch -> qualify -> transfer/disposition). The LLM is consulted only
for off-script turns via an injectable classifier, which keeps cost and latency down and makes the
core flow unit-testable without any network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import re

from .config import ScriptConfig
from .knowledge import match_knowledge
from .speech_renderer import prepare_for_speech


class State(str, Enum):
    GREETING = "greeting"
    PITCH = "pitch"
    QUALIFY = "qualify"
    TRANSFER = "transfer"
    END = "end"


class Action(str, Enum):
    SPEAK = "speak"          # say `reply`, keep listening
    TRANSFER = "transfer"    # warm-transfer to a human closer
    HANGUP = "hangup"        # disposition + end the call


class Intent(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    QUESTION = "question"
    UNCLEAR = "unclear"


Classifier = Callable[[str, str], Intent]

_POSITIVE = {
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "correct",
    "i do",
    "interested",
    "go ahead",
    "fine",
    "good",
    "well",
    "doing well",
    "i'm fine",
    "im fine",
}
_GREETING_ACK = {"good", "fine", "well", "doing well", "i'm fine", "im fine", "great"}
_CONSENT = {
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "go ahead",
    "interested",
    "correct",
    "i do",
    "all right",
    "alright",
    "got it",
    "i see",
    "sounds good",
    "that's good",
    "that is good",
    "thats good",
    "thank you",
    "thanks",
    "i'm good",
    "im good",
    "i am good",
    "all good",
}
_QUALIFY_YES = {"yes", "yeah", "yep", "sure", "correct", "absolutely", "definitely"}
_QUALIFY_NEGATION_MARKERS = (
    "don't know",
    "do not know",
    "dont know",
    "not sure",
    "don't think",
    "do not think",
    "don't believe",
    "not really",
    "i don't",
    "i do not",
    "i dont",
    "no i",
    "nope",
    "never",
    "can't",
    "cannot",
    "won't",
    "will not",
    "how i think",
    "not that",
    "i guess",
)
_DECISIONS_QUESTION_MARKERS = (
    "make your own",
    "your own decision",
    "own decisions",
    "decision",
)
_AGE_QUESTION_MARKERS = ("how old", "what age", "your age", "age are you", "years old")
_CONSENT_QUESTION_MARKERS = (
    "moment",
    "eligibility check",
    "quick check",
    "have a second",
    "fair enough",
    "thirty seconds",
    "30 seconds",
)
_PART_A_QUESTION = "Do you have Medicare Part A and Part B?"
_SCHEDULE_REPLY_MARKERS = (
    "what time works",
    "call you back",
    "works best for you tomorrow",
    "schedule",
)
_NEGATIVE = (
    "no",
    "nope",
    "not interested",
    "stop",
    "remove me",
    "don't call",
    "do not call",
    "busy",
    "later",
    "no thanks",
)
_QUESTION_MARKERS = (
    "what ",
    "how ",
    "why ",
    "who ",
    "when ",
    "where ",
    "which ",
    "is this ",
    "is it ",
    "are you ",
    "can you ",
    "do you ",
    "does ",
    "tell me ",
    "what do you want",
    "why are you calling",
    "who is calling",
    "who are you",
    "how did you get",
    "how much ",
    "is this a scam",
    "are you a scam",
)


def _matches_phrase(utterance: str, phrases: tuple[str, ...] | set[str]) -> bool:
    u = utterance.strip().lower()
    if not u:
        return False
    ordered = sorted(phrases, key=len, reverse=True)
    for phrase in ordered:
        p = phrase.strip().lower()
        if not p:
            continue
        if " " in p:
            if p in u:
                return True
        elif re.search(rf"\b{re.escape(p)}\b", u):
            return True
    return False


def _looks_like_question(utterance: str) -> bool:
    u = utterance.strip().lower()
    if not u:
        return False
    if u.endswith("?"):
        return True
    if u.startswith(("what", "how", "why", "who", "when", "where", "which", "is ", "are ", "can ", "do ")):
        return True
    return any(marker in u for marker in _QUESTION_MARKERS)


def _is_consent(utterance: str) -> bool:
    return _matches_phrase(utterance, _CONSENT)


def _has_qualify_negation(utterance: str) -> bool:
    u = utterance.strip().lower()
    if not u:
        return False
    if _matches_phrase(u, _NEGATIVE):
        return True
    return any(marker in u for marker in _QUALIFY_NEGATION_MARKERS)


_BARE_YES_WORDS = _QUALIFY_YES | {"ok", "okay", "go", "ahead"}


def _is_bare_yes(utterance: str) -> bool:
    """Short yes only — not 'Yes, I have' (avoids KB / wrong qualify advance on Part A)."""
    if _has_qualify_negation(utterance):
        return False
    u = utterance.strip().lower().rstrip(".!?")
    if not u:
        return False
    if u in ("yes", "yeah", "yep", "sure", "correct", "ok", "okay", "go ahead", "absolutely"):
        return True
    words = u.replace(",", " ").split()
    if len(words) > 2:
        return False
    if not (set(words) & _BARE_YES_WORDS):
        return False
    # "Yes, I have" / "Yeah I got it" — not a bare yes for Part A.
    if any(marker in u for marker in (" have", " i've", " i got", " already", " insurance")):
        return False
    return True


def _is_part_a_question(question: str) -> bool:
    return "part a" in (question or "").strip().lower()


def _is_qualify_yes(utterance: str) -> bool:
    """True for yes on age/decisions — Part A uses _is_bare_yes via handle()."""
    if _has_qualify_negation(utterance):
        return False
    if _is_consent(utterance):
        u = utterance.strip().lower().rstrip(".!?")
        if len(u.split()) <= 3 or _matches_phrase(u, ("i do", "yes i do", "yes i make")):
            return True
        if len(u.split()) > 3:
            return False
        return True
    u = utterance.strip().lower()
    if not u:
        return False
    if _matches_phrase(u, ("i do", "yes i do", "yes i make")):
        return True
    words = set(u.replace(",", " ").replace(".", " ").split())
    if not (words & _QUALIFY_YES):
        return False
    if len(words) <= 4:
        return True
    return False


def _is_age_question(question: str) -> bool:
    q = (question or "").strip().lower()
    return any(marker in q for marker in _AGE_QUESTION_MARKERS)


def _is_decisions_question(question: str) -> bool:
    q = (question or "").strip().lower()
    return any(marker in q for marker in _DECISIONS_QUESTION_MARKERS)


def _is_consent_question(question: str) -> bool:
    q = (question or "").strip().lower()
    return any(marker in q for marker in _CONSENT_QUESTION_MARKERS)


def _is_schedule_kb_reply(reply: str) -> bool:
    u = (reply or "").strip().lower()
    return any(marker in u for marker in _SCHEDULE_REPLY_MARKERS)


def _looks_like_medicare_script(script: ScriptConfig) -> bool:
    blob = " ".join(
        [
            script.greeting or "",
            script.pitch or "",
            " ".join(script.qualifying_questions or []),
        ]
    ).lower()
    return "medicare" in blob or "part a" in blob


def _ensure_part_a_first(questions: list[str], *, medicare: bool) -> list[str]:
    """Medicare fronter always asks Part A/B before age / other qualifies."""
    if not medicare:
        return questions
    out = list(questions)
    for i, q in enumerate(out):
        if "part a" in q.lower():
            if i == 0:
                return out
            item = out.pop(i)
            return [item, *out]
    return [_PART_A_QUESTION, *out]


def _extract_age_years(utterance: str) -> int | None:
    """Pull a plausible adult age from speech (65, I'm 75, 90 years old)."""
    u = (utterance or "").strip().lower()
    if not u:
        return None
    # Prefer patterns with age context first.
    for pattern in (
        r"\b(?:i(?:'?m| am)|age(?:\s+is)?|turned)\s*(\d{2,3})\b",
        r"\b(\d{2,3})\s*(?:years?\s*old|yrs?\s*old|years?)\b",
        r"\b(\d{2,3})\b",
    ):
        match = re.search(pattern, u)
        if not match:
            continue
        age = int(match.group(1))
        if 18 <= age <= 120:
            return age
    return None


def _age_qualify_result(utterance: str) -> str | None:
    """Return 'yes' / 'no' for an age answer, or None if not an age reply."""
    age = _extract_age_years(utterance)
    if age is None:
        return None
    # Medicare fronter: 65+ counts as qualifying; younger is an answered "no".
    return "yes" if age >= 65 else "no"


def _is_greeting_ack_only(utterance: str) -> bool:
    u = utterance.strip().lower()
    if _is_consent(u) or _looks_like_question(u):
        return False
    return _matches_phrase(u, _GREETING_ACK)


def heuristic_classifier(utterance: str, _context: str = "") -> Intent:
    u = utterance.strip().lower()
    if not u:
        return Intent.UNCLEAR
    if _looks_like_question(u):
        return Intent.QUESTION
    if _matches_phrase(u, _NEGATIVE):
        return Intent.NEGATIVE
    if _is_consent(u):
        return Intent.POSITIVE
    if _matches_phrase(u, _POSITIVE):
        return Intent.POSITIVE
    return Intent.UNCLEAR


@dataclass
class Turn:
    reply: str
    action: Action


@dataclass
class ConversationEngine:
    script: ScriptConfig = field(default_factory=ScriptConfig)
    classify: Classifier = heuristic_classifier
    answer_offscript: Optional[Callable[[str, str], str]] = None

    state: State = State.GREETING
    _qualify_idx: int = 0
    _positives: int = 0
    _negatives: int = 0
    _pitch_kb_answers: int = 0
    _max_pitch_kb_answers: int = 2
    _pitch_confirmed: bool = False
    _last_reply: str = ""
    _consent_misses: int = 0
    _unclear_at_qualify: int = 0
    _answered_kb_pre_consent: bool = False
    _pending_followup: str = ""
    _short_prompt: str = "Just a quick yes or no — do you have a moment?"
    # Active qualify list for this call (may prepend Part A stripped from pitch).
    _questions: list[str] = field(default_factory=list)

    def take_pending_followup(self) -> str:
        """Return and clear a deferred follow-up line (e.g. re-ask after KB)."""
        text = self._pending_followup.strip()
        self._pending_followup = ""
        return text

    def _queue_followup(self, text: str) -> None:
        line = (text or "").strip()
        if line:
            self._pending_followup = line

    def _active_questions(self) -> list[str]:
        return self._questions or list(self.script.qualifying_questions)

    def _consent_prompt(self) -> str:
        pitch = prepare_for_speech(self.script.pitch)
        if pitch:
            sentences = [s.strip() for s in pitch.replace("!", ".").split(".") if s.strip()]
            if sentences:
                last = sentences[-1]
                if "?" in last or last.lower().startswith(
                    ("do you", "can you", "would you", "have you")
                ):
                    return last if last.endswith("?") else f"{last}?"
        return "Do you have a moment for a quick eligibility check?"

    def _kb_only_answer(self, utterance: str) -> str | None:
        match = match_knowledge(utterance, self.script.knowledge_base)
        if not match:
            return None
        return prepare_for_speech(match.answer)

    def _try_offscript(self, utterance: str) -> str | None:
        kb = self._kb_only_answer(utterance)
        if kb:
            return kb
        if self.answer_offscript is None:
            return None
        answer = self.answer_offscript(utterance, self.state.value).strip()
        return answer or None

    def _speak_new(self, reply: str) -> Turn:
        text = reply.strip()
        self._last_reply = text
        return Turn(text, Action.SPEAK)

    def _consent_already_in_last_reply(self) -> bool:
        consent = self._consent_prompt().strip().lower()
        if not consent:
            return False
        return consent in self._last_reply.strip().lower()

    def _escalate(self) -> Turn:
        """Move forward when we would repeat the same line again."""
        if not self._pitch_confirmed:
            if self._consent_misses == 0:
                self._consent_misses += 1
                # Pitch already ends with the consent question — do not repeat it verbatim.
                if self._consent_already_in_last_reply():
                    return self._speak_new(self._short_prompt)
                return self._speak_new(self._consent_prompt())
            return self._speak_new(self._short_prompt)

        questions = self._active_questions()
        if not questions or self._qualify_idx == 0:
            return Turn("Sorry, could you repeat that?", Action.SPEAK)
        current = questions[self._qualify_idx - 1]
        if self._unclear_at_qualify == 0:
            self._unclear_at_qualify += 1
            return self._speak_new(current)
        if _is_age_question(current):
            return self._speak_new("Sorry — what age are you?")
        return self._speak_new("Sorry — could you say yes or no?")

    def _pitch_consent_question(self) -> str:
        pitch = prepare_for_speech(self.script.pitch)
        if pitch:
            sentences = [s.strip() for s in pitch.replace("!", ".").split(".") if s.strip()]
            for sentence in reversed(sentences):
                if "?" in sentence:
                    return sentence if sentence.endswith("?") else f"{sentence}?"
        return self._short_prompt

    def _respond_offscript_pitch(self, utterance: str) -> Turn | None:
        turn = self._respond_offscript(utterance)
        if not turn or self.state != State.PITCH:
            return turn
        # Speak KB only; consent question follows after playback (keeps Telnyx stream stable).
        question = self._pitch_consent_question()
        if question.strip().lower() not in turn.reply.strip().lower():
            self._queue_followup(question)
        return turn

    def _respond_offscript_pre_consent(self, utterance: str) -> Turn | None:
        turn = self._respond_offscript(utterance)
        if not turn:
            return None
        question = self._pitch_consent_question()
        if question.strip().lower() not in turn.reply.strip().lower():
            follow = (
                self._short_prompt
                if turn.reply.strip().endswith("?")
                or _matches_phrase(
                    turn.reply.lower(),
                    (
                        "fair enough",
                        "thirty-second check",
                        "30-second check",
                        "quick check",
                        "quick moment",
                    ),
                )
                else question
            )
            self._queue_followup(follow)
        return turn

    def _respond_offscript_qualify(self, utterance: str) -> Turn | None:
        turn = self._respond_offscript(utterance)
        if not turn or not self._pitch_confirmed or self._qualify_idx == 0:
            return turn
        questions = self._active_questions()
        current = questions[self._qualify_idx - 1]
        if current.strip().lower() not in turn.reply.strip().lower():
            self._queue_followup(current)
        return turn

    def _respond_offscript(self, utterance: str) -> Turn | None:
        answer = self._try_offscript(utterance)
        if not answer or answer == self._last_reply:
            return None
        # Never leave the script for callback scheduling mid-pitch / pre-consent / Part A.
        if _is_schedule_kb_reply(answer):
            if self.state == State.PITCH or (self.state == State.QUALIFY and not self._pitch_confirmed):
                return None
            if self.state == State.QUALIFY and self._qualify_idx > 0:
                current = self._active_questions()[self._qualify_idx - 1]
                if _is_part_a_question(current):
                    return None
        if self.state == State.PITCH:
            self._pitch_kb_answers += 1
        elif self.state == State.QUALIFY and not self._pitch_confirmed:
            self._answered_kb_pre_consent = True
        return self._speak_new(answer)

    def _pitch_statement_and_first_question(self) -> tuple[str, str]:
        """Split pitch into spoken lead + optional trailing question from the pitch text."""
        pitch = prepare_for_speech(self.script.pitch)
        body = pitch
        embedded = ""
        if "?" in pitch:
            candidate = self._pitch_consent_question()
            if candidate and candidate.strip().lower() in pitch.lower():
                embedded = candidate.strip()
                pos = pitch.lower().rfind(embedded.lower())
                if pos >= 0:
                    stripped = pitch[:pos].strip().rstrip(".—-,; ")
                    if stripped:
                        body = stripped
        if embedded and not embedded.endswith("?"):
            embedded = f"{embedded}?"
        return body or pitch, embedded

    def _deliver_pitch(self) -> Turn:
        self._pitch_kb_answers = 0
        self.state = State.QUALIFY
        self._answered_kb_pre_consent = False
        self._consent_misses = 0
        body, embedded = self._pitch_statement_and_first_question()
        medicare = _looks_like_medicare_script(self.script)
        questions = list(self.script.qualifying_questions)

        if embedded:
            short_ask = len(embedded.split()) <= 3
            consent_ask = _is_consent_question(embedded) or short_ask
            matches_first = bool(
                questions
                and (
                    embedded.lower()[:28] in questions[0].lower()
                    or questions[0].lower()[:28] in embedded.lower()
                )
            )
            in_qualify = any(
                embedded.lower()[:28] in q.lower() or q.lower()[:28] in embedded.lower()
                for q in questions
            )
            if consent_ask or matches_first:
                # "moment?" / pitch re-asks Q1 — wait for yes, then first qualify.
                questions = _ensure_part_a_first(questions, medicare=medicare)
                self._questions = questions
                self._pitch_confirmed = False
                self._qualify_idx = 0
                self._queue_followup(embedded)
                turn = self._speak_new(body)
                self._last_reply = f"{body} {embedded}".strip()
                return turn
            if not in_qualify:
                # Part A/B lived only in pitch — become real Q1.
                questions.insert(0, embedded)

        questions = _ensure_part_a_first(questions, medicare=medicare)
        # Telnyx-era flow: pitch body only — wait for caller, then Part A via _next_qualifier.
        self._questions = questions
        self._pitch_confirmed = False
        self._qualify_idx = 0
        return self._speak_new(body or self.script.pitch)

    def _objection_reply(self, utterance: str) -> str:
        if self.answer_offscript is not None:
            reply = self.answer_offscript(utterance, "objection").strip()
            if reply:
                return reply
        return (
            "I totally get that — it's just a quick eligibility check. "
            "Takes about thirty seconds, fair enough?"
        )

    def open(self) -> Turn:
        self.state = State.PITCH
        return self._speak_new(self.script.greeting)

    def handle(self, utterance: str) -> Turn:
        intent = self.classify(utterance, self.state.value)

        if intent == Intent.NEGATIVE:
            self._negatives += 1
            if self._negatives >= 2:
                self.state = State.END
                return Turn(self.script.not_interested_line, Action.HANGUP)
            reply = self._objection_reply(utterance)
            turn = self._speak_new(reply)
            # Soft no — re-ask the current qualify question (Part A/B, age, …).
            if self.state == State.QUALIFY and self._qualify_idx > 0:
                questions = self._active_questions()
                current = questions[self._qualify_idx - 1]
                if current.strip().lower() not in reply.lower():
                    self._queue_followup(current)
            elif self.state == State.QUALIFY and not self._pitch_confirmed:
                question = self._pitch_consent_question()
                if question and question.strip().lower() not in reply.lower():
                    self._queue_followup(
                        question if question.endswith("?") else f"{question}?"
                    )
            return turn

        is_question = intent == Intent.QUESTION or bool(self._kb_only_answer(utterance))

        if self.state == State.PITCH:
            if is_question:
                if self._pitch_kb_answers >= self._max_pitch_kb_answers:
                    return self._deliver_pitch()
                turn = self._respond_offscript_pitch(utterance)
                if turn:
                    return turn
                # No KB hit — keep the script moving (do not escalate into consent).
                return self._deliver_pitch()
            if _is_greeting_ack_only(utterance):
                return self._deliver_pitch()
            return self._deliver_pitch()

        if self.state == State.QUALIFY:
            if not self._pitch_confirmed:
                # Any affirmative after the pitch counts as consent — thank you, yes, sure, etc.
                if intent == Intent.POSITIVE or _is_consent(utterance):
                    self._pitch_confirmed = True
                    self._consent_misses = 0
                    self._answered_kb_pre_consent = False
                    return self._next_qualifier()
                if is_question:
                    turn = self._respond_offscript_pre_consent(utterance)
                    if turn:
                        return turn
                return self._escalate()

            # Age numbers first — KB triggers like "I am" / "years old" must not loop.
            if self._qualify_idx > 0:
                current_q = self._active_questions()[self._qualify_idx - 1]
                if _is_age_question(current_q):
                    age_result = _age_qualify_result(utterance)
                    if age_result == "yes":
                        self._positives += 1
                        return self._next_qualifier()
                    if age_result == "no":
                        return self._next_qualifier()
                    # Bare "I am" / preamble — wait for the number, don't skip the question.
                    u = utterance.strip().lower().rstrip(".!?")
                    if u in {"i am", "im", "i m", "i'm"}:
                        return self._escalate()
                    # "okay" / "go ahead" are consent words — never skip age for them.
                    return self._escalate()

                if _is_decisions_question(current_q):
                    # Stale age from the prior question must not advance decisions.
                    if _extract_age_years(utterance) is not None:
                        return self._escalate()
                    if _has_qualify_negation(utterance):
                        return self._escalate()

                if _is_part_a_question(current_q):
                    if _is_bare_yes(utterance):
                        self._positives += 1
                        return self._next_qualifier()
                    # "Yes, I have" — re-ask Part A; real KB questions fall through below.
                    u = utterance.strip().lower()
                    if _is_qualify_yes(utterance) and any(
                        marker in u for marker in (" have", " i've", " i got", " already")
                    ):
                        return self._escalate()
                    if is_question:
                        turn = self._respond_offscript_qualify(utterance)
                        if turn:
                            return turn
                    if self._kb_only_answer(utterance) and not is_question:
                        return self._escalate()
                    return self._escalate()

                # Other yes/no qualifies (after Part A): answer before KB.
                if _is_qualify_yes(utterance):
                    self._positives += 1
                    return self._next_qualifier()

            if self._kb_only_answer(utterance):
                turn = self._respond_offscript_qualify(utterance)
                if turn:
                    return turn

            if is_question:
                turn = self._respond_offscript_qualify(utterance)
                if turn:
                    return turn
                return self._escalate()

            if _is_qualify_yes(utterance):
                self._positives += 1
                return self._next_qualifier()

            return self._escalate()

        if self.state == State.TRANSFER:
            return Turn(self.script.transfer_line, Action.TRANSFER)

        return Turn("Sorry, could you repeat that?", Action.SPEAK)

    def _next_qualifier(self) -> Turn:
        self._unclear_at_qualify = 0
        questions = self._active_questions()
        if self._qualify_idx < len(questions):
            q = questions[self._qualify_idx]
            self._qualify_idx += 1
            return self._speak_new(q)

        if self._positives >= max(1, len(questions) // 2 + len(questions) % 2):
            self.state = State.TRANSFER
            return Turn(self.script.transfer_line, Action.TRANSFER)

        self.state = State.END
        return Turn(self.script.not_interested_line, Action.HANGUP)
