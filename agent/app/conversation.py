"""Pure conversation state machine for the fronter.

Deterministic flow (greet -> pitch -> qualify -> transfer/disposition). The LLM is consulted only
for off-script turns via an injectable classifier, which keeps cost and latency down and makes the
core flow unit-testable without any network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .config import ScriptConfig


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


# A classifier maps (utterance, context) -> Intent. Inject an LLM-backed one in production;
# the default heuristic keeps tests offline.
Classifier = Callable[[str, str], Intent]


_POSITIVE = {"yes", "yeah", "yep", "sure", "ok", "okay", "correct", "i do", "interested", "go ahead"}
_NEGATIVE = {"no", "nope", "not interested", "stop", "remove me", "don't call", "busy", "later"}


def heuristic_classifier(utterance: str, _context: str = "") -> Intent:
    u = utterance.strip().lower()
    if not u:
        return Intent.UNCLEAR
    if any(p in u for p in _NEGATIVE):
        return Intent.NEGATIVE
    if u.endswith("?") or u.startswith(("what", "how", "why", "who", "when", "where")):
        return Intent.QUESTION
    if any(p in u for p in _POSITIVE):
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
    # Optional LLM responder for off-script questions: (question, context) -> answer text.
    answer_offscript: Optional[Callable[[str, str], str]] = None

    state: State = State.GREETING
    _qualify_idx: int = 0
    _positives: int = 0
    _negatives: int = 0

    def open(self) -> Turn:
        """First thing the bot says when the call connects."""
        self.state = State.PITCH
        return Turn(self.script.greeting, Action.SPEAK)

    def handle(self, utterance: str) -> Turn:
        """Process one caller utterance and return the bot's next move."""
        intent = self.classify(utterance, self.state.value)

        if intent == Intent.NEGATIVE:
            self._negatives += 1
            if self._negatives >= 2 or self.state in (State.GREETING, State.PITCH):
                self.state = State.END
                return Turn(self.script.not_interested_line, Action.HANGUP)

        if intent == Intent.QUESTION and self.answer_offscript is not None:
            answer = self.answer_offscript(utterance, self.state.value)
            return Turn(answer, Action.SPEAK)

        if self.state == State.PITCH:
            self.state = State.QUALIFY
            self._qualify_idx = 0
            return Turn(self.script.pitch, Action.SPEAK)

        if self.state == State.QUALIFY:
            if intent == Intent.POSITIVE:
                self._positives += 1
            return self._next_qualifier()

        if self.state == State.TRANSFER:
            return Turn(self.script.transfer_line, Action.TRANSFER)

        # Fallback: keep the conversation moving.
        return Turn("Sorry, could you repeat that?", Action.SPEAK)

    def _next_qualifier(self) -> Turn:
        questions = self.script.qualifying_questions
        if self._qualify_idx < len(questions):
            q = questions[self._qualify_idx]
            self._qualify_idx += 1
            return Turn(q, Action.SPEAK)

        # All qualifiers asked. Qualified if a majority were positive.
        if self._positives >= max(1, len(questions) // 2 + len(questions) % 2):
            self.state = State.TRANSFER
            return Turn(self.script.transfer_line, Action.TRANSFER)

        self.state = State.END
        return Turn(self.script.not_interested_line, Action.HANGUP)
