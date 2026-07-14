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
_CONSENT = {"yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "interested", "correct", "i do"}
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
    u = utterance.strip().lower()
    if not u:
        return False
    if _matches_phrase(u, ("i do", "i have")):
        return True
    words = set(u.replace(",", " ").replace(".", " ").split())
    return bool(words & _QUALIFY_YES)


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
    _short_prompt: str = "Just a quick yes or no — do you have a moment?"

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

    def _escalate(self) -> Turn:
        """Move forward when we would repeat the same line again."""
        if not self._pitch_confirmed:
            if self._consent_misses == 0:
                self._consent_misses += 1
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

    def _respond_offscript(self, utterance: str) -> Turn | None:
        answer = self._try_offscript(utterance)
        if not answer or answer == self._last_reply:
            return None
        if self.state == State.PITCH:
            self._pitch_kb_answers += 1
        return self._speak_new(answer)

    def _deliver_pitch(self) -> Turn:
        self._pitch_kb_answers = 0
        self.state = State.QUALIFY
        self._qualify_idx = 0
        self._pitch_confirmed = False
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
            if is_question:
                if self._pitch_kb_answers >= self._max_pitch_kb_answers:
                    return self._deliver_pitch()
                turn = self._respond_offscript(utterance)
                if turn:
                    return turn
                return self._escalate()
            if _is_greeting_ack_only(utterance):
                return self._deliver_pitch()
            return self._deliver_pitch()

        if self.state == State.QUALIFY:
            if not self._pitch_confirmed:
                if intent == Intent.POSITIVE and _is_consent(utterance):
                    self._pitch_confirmed = True
                    self._consent_misses = 0
                    return self._next_qualifier()
                if is_question:
                    turn = self._respond_offscript(utterance)
                    if turn:
                        return turn
                return self._escalate()

            if self._kb_only_answer(utterance):
                turn = self._respond_offscript(utterance)
                if turn:
                    return turn

            if is_question:
                turn = self._respond_offscript(utterance)
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
