from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os

load_dotenv()


class ScriptConfig(BaseModel):
    """A campaign's fronter script. Loaded per call from the dashboard/DB in production."""

    greeting: str = "Hi, this is Alex calling on a recorded line. How are you today?"
    pitch: str = (
        "Great — I'll be quick. We help homeowners cut their electricity bill with no upfront cost. "
        "Do you currently own your home?"
    )
    qualifying_questions: list[str] = Field(
        default_factory=lambda: [
            "Do you own your home?",
            "Is your average monthly electric bill over 100 dollars?",
        ]
    )
    # If the lead is qualified + interested, transfer to a human closer.
    transfer_line: str = "Perfect — let me connect you with a specialist right now, one moment."
    not_interested_line: str = "No problem at all, thanks for your time. Have a great day!"

    @classmethod
    def load(cls, path: str | None = None) -> "ScriptConfig":
        if path and Path(path).exists():
            return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
        return cls()


class Settings(BaseModel):
    deepgram_api_key: str = Field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))
    google_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    fish_api_key: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_API_KEY", ""))
    fish_model: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_MODEL", "s1"))
    fish_reference_id: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_REFERENCE_ID", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))

    vicidial_base_url: str = Field(default_factory=lambda: os.getenv("VICIDIAL_BASE_URL", ""))
    vicidial_user: str = Field(default_factory=lambda: os.getenv("VICIDIAL_API_USER", ""))
    vicidial_pass: str = Field(default_factory=lambda: os.getenv("VICIDIAL_API_PASS", ""))
    vicidial_transfer_preset: str = Field(
        default_factory=lambda: os.getenv("VICIDIAL_TRANSFER_PRESET", "CLOSER")
    )

    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8765")))


settings = Settings()
