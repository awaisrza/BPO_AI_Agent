"""Minimal ViciDial integration: warm transfer + disposition.

ViciDial exposes an Agent API (`/agc/api.php`) and a Non-Agent API (`/vicidial/non_agent_api.php`).
Exact function names/params depend on the dialer's configuration, so treat these as the integration
seam to validate against the target BPO's ViciDial during onboarding.
"""

from __future__ import annotations

import httpx
import re
from loguru import logger

from .config import settings

_VD_CALL_ID_RE = re.compile(r"\b([MVY][A-Za-z0-9-]{11,})\b")


def looks_like_vicidial_call_id(value: str) -> bool:
    """ViciDial call IDs are ~20 chars and start with M, V, or Y (ra_call_control value)."""
    token = (value or "").strip()
    if len(token) < 12:
        return False
    return token[0] in ("M", "V", "Y") and token[1:].replace("-", "").isalnum()


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

    async def _non_agent_api(self, params: dict) -> str:
        url = f"{self.base_url}/vicidial/non_agent_api.php"
        base = {
            "source": "ai-fronter",
            "user": self.api_user,
            "pass": self.api_pass,
        }
        resp = await self._client.get(url, params={**base, **params})
        resp.raise_for_status()
        logger.debug(f"ViciDial non_agent_api {params.get('function')}: {resp.text.strip()[:200]}")
        return resp.text.strip()

    @staticmethod
    def _parse_call_id_from_csv(text: str, *, agent_user: str | None = None) -> str | None:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines or lines[0].upper().startswith("ERROR:"):
            return None
        header = [h.strip().lower() for h in lines[0].split(",")]
        id_cols = [i for i, name in enumerate(header) if name in ("call_id", "callerid")]
        data_lines = lines[1:] if id_cols else lines
        if not id_cols and len(header) > 1 and looks_like_vicidial_call_id(header[1]):
            return header[1]
        for line in data_lines:
            if agent_user and agent_user not in line:
                continue
            if id_cols:
                cols = line.split(",")
                for idx in id_cols:
                    if idx < len(cols):
                        token = cols[idx].strip()
                        if looks_like_vicidial_call_id(token):
                            return token
            for match in _VD_CALL_ID_RE.finditer(line):
                token = match.group(1)
                if looks_like_vicidial_call_id(token):
                    return token
        return None

    @staticmethod
    def _extract_call_id_from_api_text(text: str, agent_user: str | None = None) -> str | None:
        """Pull M/V/Y call id from Agent or Non-Agent API CSV/text."""
        parsed = ViciDialClient._parse_call_id_from_csv(text, agent_user=agent_user)
        if parsed:
            return parsed
        if not text or text.strip().upper().startswith("ERROR:"):
            return None
        if agent_user:
            for line in text.splitlines():
                if agent_user not in line:
                    continue
                for match in _VD_CALL_ID_RE.finditer(line):
                    token = match.group(1)
                    if looks_like_vicidial_call_id(token):
                        return token
        for match in _VD_CALL_ID_RE.finditer(text):
            token = match.group(1)
            if looks_like_vicidial_call_id(token):
                return token
        return None

    async def lookup_active_call_id(self, agent_user: str) -> str | None:
        """Resolve remote-agent call ID for ra_call_control (agent_status / live_agents)."""
        if not self.base_url or not self.api_user or not self.api_pass:
            logger.warning("ViciDial call ID lookup skipped — missing API base_url/user/pass")
            return None
        agent_user = (agent_user or "").strip()
        if not agent_user:
            return None
        probes: list[tuple[str, dict, str]] = [
            (
                "agent_status",
                {
                    "function": "agent_status",
                    "agent_user": agent_user,
                    "stage": "csv",
                    "header": "YES",
                },
                "non_agent",
            ),
            (
                "logged_in_agents",
                {
                    "function": "logged_in_agents",
                    "stage": "csv",
                    "header": "YES",
                    "user_groups": "-ALL-",
                },
                "non_agent",
            ),
            (
                "st_get_agent_active_lead",
                {"function": "st_get_agent_active_lead", "agent_user": agent_user, "value": agent_user},
                "agent",
            ),
        ]
        last_error = ""
        for label, params, api_kind in probes:
            try:
                if api_kind == "non_agent":
                    result = await self._non_agent_api(params)
                else:
                    result = await self._agent_api(params)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"ViciDial {label} lookup failed: {exc}")
                last_error = str(exc)
                continue
            if result.strip().upper().startswith("ERROR:"):
                last_error = result.strip()[:160]
                logger.debug(f"ViciDial {label}: {last_error}")
                continue
            call_id = self._extract_call_id_from_api_text(result, agent_user=agent_user)
            if call_id:
                logger.info(f"ViciDial call ID from {label}: {call_id}")
                return call_id
        if last_error:
            logger.warning(f"ViciDial call ID lookup empty for {agent_user}: {last_error}")
        return None

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
