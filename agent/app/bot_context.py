"""Per-bot runtime context from Supabase (script, ViciDial mapping, org creds)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import ScriptConfig
from .vicidial import ViciDialClient


@dataclass(frozen=True)
class VicidialOrgConfig:
    base_url: str
    api_user: str
    api_pass: str
    transfer_preset: str


@dataclass(frozen=True)
class BotRunContext:
    script: ScriptConfig
    bot_id: str | None
    bot_name: str
    agent_user: str
    vicidial_campaign_id: str | None
    org_id: str | None
    vicidial: VicidialOrgConfig | None

    def vicidial_client(self) -> ViciDialClient | None:
        if not self.vicidial:
            return None
        return ViciDialClient(
            base_url=self.vicidial.base_url,
            api_user=self.vicidial.api_user,
            api_pass=self.vicidial.api_pass,
        )

    @property
    def transfer_preset(self) -> str:
        if self.vicidial:
            return self.vicidial.transfer_preset
        return "CLOSER"
