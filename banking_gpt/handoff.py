from __future__ import annotations

from enum import StrEnum

from banking_gpt.evidence import EvidenceRecorder
from banking_gpt.models import InterventionRequest
from banking_gpt.surface import PlaywrightBrowserAdapter


class ControlOwner(StrEnum):
    AUTOMATION = "automation"
    HUMAN = "human"


class HandoffCoordinator:
    def __init__(self) -> None:
        self.owner = ControlOwner.AUTOMATION

    async def hand_to_human(
        self,
        request: InterventionRequest,
        surface: PlaywrightBrowserAdapter,
        evidence: EvidenceRecorder,
    ) -> None:
        if self.owner != ControlOwner.AUTOMATION:
            raise RuntimeError("Control is not currently owned by automation")
        self.owner = ControlOwner.HUMAN
        evidence.event("human_control_started", intervention=request.model_dump(mode="json"))
        await surface.manual_takeover()
        print("\nHuman intervention requested. Use the open browser window.")
        print(f"Reason: {request.message}")
        await __import__("asyncio").to_thread(input, "Press Enter when control can return: ")
        self.owner = ControlOwner.AUTOMATION
        evidence.event("human_control_ended", intervention_id=request.id)

