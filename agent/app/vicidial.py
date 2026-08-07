"""Minimal ViciDial integration: warm transfer + disposition.

ViciDial exposes an Agent API (`/agc/api.php`) and a Non-Agent API (`/vicidial/non_agent_api.php`).
Exact function names/params depend on the dialer's configuration, so treat these as the integration
seam to validate against the target BPO's ViciDial during onboarding.
"""

from __future__ import annotations

import httpx
from loguru import logger

from .config import settings


class ViciDialClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_user: str | None = None,
        api_pass: str | None = None,
    ):
        self.base_url = (base_url or settings.vicidial_base_url).rstrip("/")
        self.api_user = api_user or settings.vicidial_user
        self.api_pass = api_pass or settings.vicidial_pass
        self._client = httpx.AsyncClient(timeout=15.0)

    async def _agent_api(self, params: dict) -> str:
        url = f"{self.base_url}/agc/api.php"
        base = {
            "source": "ai-fronter",
            "user": self.api_user,
            "pass": self.api_pass,
        }
        resp = await self._client.get(url, params={**base, **params})
        resp.raise_for_status()
        logger.debug(f"ViciDial agent_api {params.get('function')}: {resp.text.strip()}")
        return resp.text.strip()

    async def warm_transfer(
        self,
        agent_user: str,
        *,
        preset: str | None = None,
        closer_user: str | None = None,
    ) -> str:
        """Transfer the live call to a closer queue or a specific logged-in agent."""
        if closer_user:
            return await self._agent_api(
                {
                    "function": "transfer_conference",
                    "agent_user": agent_user,
                    "value": "LOCAL_CLOSER",
                    "ingroup_choices": "AGENTDIRECT",
                    "phone_number": closer_user,
                }
            )

        preset = preset or settings.vicidial_transfer_preset
        return await self._agent_api(
            {
                "function": "transfer_conference",
                "agent_user": agent_user,
                "value": "DIAL_WITH_CUSTOMER",
                "preset": preset,
            }
        )

    async def ra_call_control(
        self,
        agent_user: str,
        call_id: str,
        *,
        stage: str,
        ingroup_choices: str | None = None,
        phone_number: str | None = None,
        status: str | None = None,
    ) -> str:
        """Remote-agent call control (hangup / blind transfer). Requires ViciDial call ID."""
        params: dict[str, str] = {
            "function": "ra_call_control",
            "agent_user": agent_user,
            "value": call_id,
            "stage": stage,
        }
        if ingroup_choices:
            params["ingroup_choices"] = ingroup_choices
        if phone_number:
            params["phone_number"] = phone_number
        if status:
            params["status"] = status
        result = await self._agent_api(params)
        logger.info(f"ViciDial ra_call_control {stage}: {result[:200]}")
        return result

    async def remote_agent_transfer(
        self,
        agent_user: str,
        call_id: str,
        *,
        ingroup: str | None = None,
        extension: str | None = None,
        status: str = "XFER",
    ) -> str:
        """Blind transfer for a remote agent seat (e.g. AI bot on AudioSocket)."""
        if extension:
            return await self.ra_call_control(
                agent_user,
                call_id,
                stage="EXTENSIONTRANSFER",
                phone_number=extension,
                status=status,
            )
        ingroup = (ingroup or "DEFAULTINGROUP").strip() or "DEFAULTINGROUP"
        return await self.ra_call_control(
            agent_user,
            call_id,
            stage="INGROUPTRANSFER",
            ingroup_choices=ingroup,
            status=status,
        )

    async def remote_agent_hangup(
        self, agent_user: str, call_id: str, *, status: str = "NI"
    ) -> str:
        return await self.ra_call_control(
            agent_user, call_id, stage="HANGUP", status=status
        )

    @staticmethod
    def api_succeeded(result: str) -> bool:
        return result.strip().upper().startswith("SUCCESS:")

    async def set_disposition(self, agent_user: str, status: str) -> str:
        """Set the call status (e.g. 'XFER', 'NI' for not interested, 'AM' for answering machine)."""
        return await self._agent_api(
            {
                "function": "external_status",
                "agent_user": agent_user,
                "value": status,
            }
        )

    async def change_campaign(self, agent_user: str, campaign_id: str) -> str:
        """Point a ViciDial agent seat at the outbound campaign hopper."""
        return await self._agent_api(
            {
                "function": "change_campaign",
                "agent_user": agent_user,
                "value": campaign_id,
            }
        )

    async def resume_agent(self, agent_user: str) -> str:
        """Unpause agent so ViciDial auto-dialer can feed calls."""
        return await self._agent_api(
            {
                "function": "external_pause",
                "agent_user": agent_user,
                "value": "RESUME",
            }
        )

    async def prepare_for_dialing(self, agent_user: str, campaign_id: str) -> None:
        """Map agent to campaign and resume — BPO must have campaign active + leads in hopper."""
        result = await self.change_campaign(agent_user, campaign_id)
        logger.info(f"ViciDial change_campaign({agent_user} -> {campaign_id}): {result[:120]}")
        result = await self.resume_agent(agent_user)
        logger.info(f"ViciDial resume_agent({agent_user}): {result[:120]}")

    async def hangup(self, agent_user: str) -> str:
        return await self._agent_api(
            {"function": "external_hangup", "agent_user": agent_user, "value": "1"}
        )

    async def close(self) -> None:
        await self._client.aclose()
