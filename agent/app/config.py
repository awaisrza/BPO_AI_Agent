from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os

_AGENT_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _AGENT_ROOT.parent
for _env_path in (
    _AGENT_ROOT / ".env.example",
    _REPO_ROOT / ".env.local",
    _REPO_ROOT / "dashboard" / ".env.local",
    _AGENT_ROOT / ".env",
    _AGENT_ROOT / ".env.local",
):
    if _env_path.exists():
        load_dotenv(_env_path, override=True)


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
    transfer_line: str = "Perfect — let me connect you with a specialist right now, one moment."
    not_interested_line: str = "No problem at all, thanks for your time. Have a great day!"
    transfer_preset: str | None = None

    @classmethod
    def from_script_json(cls, data: dict) -> "ScriptConfig":
        """Build from dashboard `campaigns.script_json`."""
        questions = data.get("qualifying_questions") or []
        if isinstance(questions, list):
            questions = [str(q).strip() for q in questions if str(q).strip()]
        return cls(
            greeting=str(data.get("greeting", "")).strip(),
            pitch=str(data.get("pitch", "")).strip(),
            qualifying_questions=questions,
            transfer_line=str(
                data.get("transfer_line") or "Perfect — let me connect you with a specialist right now, one moment."
            ),
            not_interested_line=str(
                data.get("not_interested_line") or "No problem at all, thanks for your time. Have a great day!"
            ),
            transfer_preset=data.get("transfer_preset"),
        )

    @classmethod
    def load(cls, path: str | None = None) -> "ScriptConfig":
        if path and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if "greeting" in raw:
                return cls.from_script_json(raw)
            return cls(**raw)
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

    supabase_url: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    )
    supabase_service_role_key: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )


settings = Settings()
