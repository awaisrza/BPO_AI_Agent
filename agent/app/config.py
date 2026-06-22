from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os

from .models import KnowledgeEntry

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
    transfer_closer_user: str | None = None
    transfer_closer_name: str | None = None
    knowledge_base: list[KnowledgeEntry] = Field(default_factory=list)

    @classmethod
    def from_script_json(cls, data: dict) -> "ScriptConfig":
        """Build from dashboard `campaigns.script_json`."""
        from .knowledge import parse_knowledge_base

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
            transfer_closer_user=data.get("transfer_closer_user"),
            transfer_closer_name=data.get("transfer_closer_name"),
            knowledge_base=parse_knowledge_base(data.get("knowledge_base")),
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
    # managed = Deepgram + Fish. chatterbox = Whisper + Chatterbox (GPU). gpu = Whisper + Piper.
    voice_backend: str = Field(
        default_factory=lambda: os.getenv("VOICE_BACKEND", "managed").strip().lower()
    )

    deepgram_api_key: str = Field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))
    google_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    fish_api_key: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_API_KEY", ""))
    fish_model: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_MODEL", "s1"))
    fish_reference_id: str = Field(default_factory=lambda: os.getenv("FISH_AUDIO_REFERENCE_ID", ""))
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))

    whisper_model: str = Field(
        default_factory=lambda: os.getenv("WHISPER_MODEL", "distil-large-v2")
    )
    whisper_device: str = Field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "auto"))
    whisper_compute_type: str = Field(
        default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")
    )

    piper_exe: str = Field(default_factory=lambda: os.getenv("PIPER_EXE", ""))
    piper_model: str = Field(default_factory=lambda: os.getenv("PIPER_MODEL", ""))
    piper_speaker: int = Field(
        default_factory=lambda: int(os.getenv("PIPER_SPEAKER", "0") or "0")
    )

    chatterbox_reference_audio: str = Field(
        default_factory=lambda: os.getenv("CHATTERBOX_REFERENCE_AUDIO", "")
    )
    chatterbox_device: str = Field(
        default_factory=lambda: os.getenv("CHATTERBOX_DEVICE", "auto")
    )
    chatterbox_exaggeration: float = Field(
        default_factory=lambda: float(os.getenv("CHATTERBOX_EXAGGERATION", "0.35") or "0.35")
    )
    chatterbox_cfg_weight: float = Field(
        default_factory=lambda: float(os.getenv("CHATTERBOX_CFG_WEIGHT", "0.5") or "0.5")
    )

    speech_max_words: int = Field(
        default_factory=lambda: int(os.getenv("SPEECH_MAX_WORDS", "14") or "14")
    )
    speech_pause_min_ms: int = Field(
        default_factory=lambda: int(os.getenv("SPEECH_PAUSE_MIN_MS", "400") or "400")
    )
    speech_pause_max_ms: int = Field(
        default_factory=lambda: int(os.getenv("SPEECH_PAUSE_MAX_MS", "700") or "700")
    )

    vicidial_base_url: str = Field(default_factory=lambda: os.getenv("VICIDIAL_BASE_URL", ""))
    vicidial_user: str = Field(default_factory=lambda: os.getenv("VICIDIAL_API_USER", ""))
    vicidial_pass: str = Field(default_factory=lambda: os.getenv("VICIDIAL_API_PASS", ""))
    vicidial_transfer_preset: str = Field(
        default_factory=lambda: os.getenv("VICIDIAL_TRANSFER_PRESET", "CLOSER")
    )

    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8765")))

    twilio_account_sid: str = Field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = Field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_from_number: str = Field(default_factory=lambda: os.getenv("TWILIO_FROM_NUMBER", ""))
    # Public HTTPS URL (ngrok/cloudflare tunnel) — Twilio webhooks cannot reach localhost
    local_server_url: str = Field(default_factory=lambda: os.getenv("LOCAL_SERVER_URL", ""))

    supabase_url: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    )
    supabase_service_role_key: str = Field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )


settings = Settings()
