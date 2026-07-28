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
_GREETING_REPLY = _GREETING_ACK | {"i'm good", "im good", "i am good", "all good"}
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
}
_QUALIFY_YES = {"yes", "yeah", "yep", "sure", "correct", "absolutely", "definitely"}
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


def _is_qualify_yes(utterance: str) -> bool:
    if _is_consent(utterance):
        return True
    u = utterance.strip().lower()
    if not u:
        return False
    if _matches_phrase(u, ("i do", "i have")):
        return True
    words = set(u.replace(",", " ").replace(".", " ").split())
    return bool(words & _QUALIFY_YES)


_AGE_QUESTION_MARKERS = ("how old", "your age", "what age")


def _qualifier_expects_age(question: str) -> bool:
    q = question.strip().lower()
    return any(marker in q for marker in _AGE_QUESTION_MARKERS)


def _parse_age_years(utterance: str) -> int | None:
    """Extract age from replies like 'I'm 60', 'my age is 60', or '60 years old'."""
    u = utterance.strip().lower().replace(",", " ")
    patterns = (
        r"\b(?:i'?m|i am|im)\s+(\d{1,3})\b",
        r"\b(?:my age is|age is)\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:years?\s*old)\b",
        r"^\s*(\d{1,3})\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, u)
        if match:
            age = int(match.group(1))
            if 1 <= age <= 120:
                return age
    return None


def _age_in_qualify_range(age: int, *, min_age: int, max_age: int) -> bool:
    return min_age <= age <= max_age


def _is_qualify_answer(utterance: str, current_question: str | None) -> bool:
    if current_question and _qualifier_expects_age(current_question):
        return _parse_age_years(utterance) is not None
    if _is_qualify_yes(utterance):
        return True
    return False


def _is_greeting_reply(utterance: str) -> bool:
    """Answer to 'how are you today?' — always play the pitch, never a KB line."""
    u = utterance.strip().lower().rstrip(".")
    if _looks_like_question(u):
        return False
    if _matches_phrase(
        u,
        {
            "i'm good",
            "im good",
            "i am good",
            "all good",
            "i'm fine",
            "im fine",
            "doing well",
            "doing good",
            "i'm doing good",
            "im doing good",
            "being good",
            "i'm being good",
            "im being good",
            "been good",
        },
    ):
        return True
    words = [w for w in u.replace(",", " ").split() if w]
    return len(words) == 1 and words[0] in {"good", "fine", "well", "great"}


def _is_greeting_ack_only(utterance: str) -> bool:
    u = utterance.strip().lower()
    if _is_consent(u) or _looks_like_question(u):
        return False
    return _matches_phrase(u, _GREETING_ACK)


def heuristic_classifier(utterance: str, _context: str = "") -> Intent:
    u = utterance.strip().lower()
    if not u:
        return Intent.UNCLEAR
    # "Yes?" / "Yeah?" are consent — not real questions (STT often adds "?").
    if u.endswith("?"):
        core = u.rstrip("?").strip()
        if not _looks_like_question(core) and (
            _is_consent(core) or _matches_phrase(core, _QUALIFY_YES)
        ):
            return Intent.POSITIVE
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

    def take_pending_followup(self) -> str:
        """Return and clear a deferred follow-up line (e.g. re-ask after KB)."""
        text = self._pending_followup.strip()
        self._pending_followup = ""
        return text

    def _queue_followup(self, text: str) -> None:
        line = (text or "").strip()
        if line:
            self._pending_followup = line

    def _current_qualifier_question(self) -> str | None:
        if self._qualify_idx <= 0:
            return None
        questions = self.script.qualifying_questions
        idx = self._qualify_idx - 1
        if idx < len(questions):
            return questions[idx]
        return None

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

        questions = self.script.qualifying_questions
        if not questions or self._qualify_idx == 0:
            return Turn("Sorry, could you repeat that?", Action.SPEAK)
        current = questions[self._qualify_idx - 1]
        if self._unclear_at_qualify == 0:
            self._unclear_at_qualify += 1
            return self._speak_new(current)
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
        questions = self.script.qualifying_questions
        current = questions[self._qualify_idx - 1]
        if current.strip().lower() not in turn.reply.strip().lower():
            self._queue_followup(current)
        return turn

    def _respond_offscript(self, utterance: str) -> Turn | None:
        answer = self._try_offscript(utterance)
        if not answer or answer == self._last_reply:
            return None
        if self.state == State.PITCH:
            self._pitch_kb_answers += 1
        elif self.state == State.QUALIFY and not self._pitch_confirmed:
            self._answered_kb_pre_consent = True
        return self._speak_new(answer)

    def _deliver_pitch(self) -> Turn:
        self._pitch_kb_answers = 0
        self.state = State.QUALIFY
        self._qualify_idx = 0
        self._pitch_confirmed = False
        self._answered_kb_pre_consent = False
        return self._speak_new(self.script.pitch)

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
            return self._speak_new(self._objection_reply(utterance))

        is_question = intent == Intent.QUESTION or bool(self._kb_only_answer(utterance))

        if self.state == State.PITCH:
            # Greeting replies must win over KB false positives (e.g. "good" overlapping
            # "not a good time") and over loose POSITIVE token matches.
            if _is_greeting_reply(utterance) or _is_greeting_ack_only(utterance):
                return self._deliver_pitch()
            if is_question:
                if self._pitch_kb_answers >= self._max_pitch_kb_answers:
                    return self._deliver_pitch()
                turn = self._respond_offscript_pitch(utterance)
                if turn:
                    return turn
                # No KB hit — keep the script moving (do not escalate into consent).
                return self._deliver_pitch()
            return self._deliver_pitch()

        if self.state == State.QUALIFY:
            if not self._pitch_confirmed:
                # Greeting reply ("I'm good") is not pitch consent — e.g. after spurious STT
                # during the hello line advanced state to QUALIFY without a real pitch answer.
                if _is_greeting_reply(utterance) or _is_greeting_ack_only(utterance):
                    return self._deliver_pitch()
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

            if self._kb_only_answer(utterance):
                turn = self._respond_offscript_qualify(utterance)
                if turn:
                    return turn

            if is_question:
                turn = self._respond_offscript_qualify(utterance)
                if turn:
                    return turn
                return self._escalate()

            current_q = self._current_qualifier_question()
            if current_q and _qualifier_expects_age(current_q):
                age = _parse_age_years(utterance)
                if age is not None:
                    if _age_in_qualify_range(
                        age,
                        min_age=self.script.qualify_age_min,
                        max_age=self.script.qualify_age_max,
                    ):
                        self._positives += 1
                        return self._next_qualifier()
                    self.state = State.END
                    return Turn(self.script.not_interested_line, Action.HANGUP)

            if _is_qualify_answer(utterance, current_q):
                self._positives += 1
                return self._next_qualifier()

            return self._escalate()

        if self.state == State.TRANSFER:
            return Turn(self.script.transfer_line, Action.TRANSFER)

        return Turn("Sorry, could you repeat that?", Action.SPEAK)

    def _next_qualifier(self) -> Turn:
        self._unclear_at_qualify = 0
        questions = self.script.qualifying_questions
        if self._qualify_idx < len(questions):
            q = questions[self._qualify_idx]
            self._qualify_idx += 1
            return self._speak_new(q)

        if self._positives >= max(1, len(questions) // 2 + len(questions) % 2):
            self.state = State.TRANSFER
            return Turn(self.script.transfer_line, Action.TRANSFER)

        self.state = State.END
        return Turn(self.script.not_interested_line, Action.HANGUP)
