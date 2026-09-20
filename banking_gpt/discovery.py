from __future__ import annotations

import json
from pathlib import Path

from banking_gpt.evidence import EvidenceRecorder
from banking_gpt.models import (
    ActionType,
    ArtifactStep,
    AutomationPolicy,
    CapabilityArtifact,
    Goal,
    InputDefinition,
    Locator,
    LocatorStrategy,
    OutcomeRule,
    OutputDefinition,
    ProposedAction,
    RecoveryRule,
    RiskLevel,
    SurfaceType,
    Target,
)
from banking_gpt.policy import PolicyEngine, PolicyViolation
from banking_gpt.providers import DiscoveryModel
from banking_gpt.surface import SurfaceAdapter, SurfaceError


class DiscoveryEngine:
    def __init__(
        self,
        surface: SurfaceAdapter,
        model: DiscoveryModel,
        evidence: EvidenceRecorder,
        policy: AutomationPolicy,
    ) -> None:
        self.surface = surface
        self.model = model
        self.evidence = evidence
        self.policy = PolicyEngine(policy)

    async def run(self, goal: Goal, target: Target) -> list[ProposedAction]:
        history: list[ProposedAction] = []
        self.policy.check_url(str(target.entry_point))
        await self.surface.start(target)
        self.evidence.event("discovery_started", goal=goal.description)
        try:
            for step_number in range(1, self.policy.policy.max_steps + 1):
                screenshot = self.evidence.screenshot_path(f"discovery-{step_number:02d}")
                observation = await self.surface.observe(screenshot)
                self.evidence.event(
                    "observation", step=step_number, observation=observation.model_dump(mode="json")
                )
                action = await self.model.decide(goal, observation, history)
                self.evidence.event(
                    "model_action", step=step_number, action=action.model_dump(mode="json")
                )
                self.policy.check_action(action)
                if action.action == ActionType.REQUEST_HELP:
                    raise RuntimeError("Model requested human intervention")
                if action.action == ActionType.COMPLETE:
                    self.evidence.event("discovery_completed", steps=len(history))
                    return history
                value = await self.surface.execute(action)
                history.append(action)
                if action.action == ActionType.EXTRACT:
                    self.evidence.event("output_extracted", name=action.output_name, value=value)
                    self.evidence.event(
                        "discovery_completed",
                        steps=len(history),
                        stopping_condition="declared_output_extracted",
                    )
                    return history
            raise RuntimeError("Discovery reached the maximum number of steps")
        except (PolicyViolation, SurfaceError, ValueError) as exc:
            self.evidence.event("discovery_failed", error=str(exc))
            raise
        finally:
            await self.surface.close(self.evidence.trace_path())


def compile_balance_artifact(
    actions: list[ProposedAction],
    *,
    member_id: str,
    entry_point: str,
) -> CapabilityArtifact:
    """Compile the demo discovery into a reviewable parameterized capability."""
    steps: list[ArtifactStep] = []
    for index, action in enumerate(actions, start=1):
        value = "{{member_id}}" if action.value == member_id else action.value
        targets = action.target
        if action.action == ActionType.EXTRACT and action.output_name == "balance":
            targets = [
                Locator(
                    strategy=LocatorStrategy.TEST_ID,
                    value="checking-balance",
                    priority=1,
                ),
                Locator(
                    strategy=LocatorStrategy.CSS,
                    value="tr[data-account-type='checking'] td:last-child",
                    priority=2,
                ),
            ]
            value = None
        steps.append(
            ArtifactStep(
                id=f"discovered-step-{index}",
                action=action.action,
                target=targets,
                value=value,
                output_name=action.output_name,
                risk=RiskLevel.READ_ONLY,
                description=action.explanation,
            )
        )
    return CapabilityArtifact(
        name="read_checking_balance_discovered",
        description="Capability generated from a successful discovery run.",
        application="mock-bank",
        surface_type=SurfaceType.BROWSER,
        entry_point=entry_point,
        inputs=[
            InputDefinition(
                name="member_id",
                type="string",
                description="Fictional internal member identifier",
                sensitive=True,
            )
        ],
        outputs=[
            OutputDefinition(
                name="balance",
                type="string",
                description="Displayed checking-account balance",
                sensitive=True,
            )
        ],
        allowed_hosts=["127.0.0.1", "localhost"],
        steps=steps,
        business_outcomes=[
            OutcomeRule(
                code="member_not_found",
                locator=Locator(strategy=LocatorStrategy.TEST_ID, value="member-not-found"),
                message="No member exists with the supplied identifier.",
            ),
            OutcomeRule(
                code="permission_denied",
                locator=Locator(strategy=LocatorStrategy.TEST_ID, value="permission-denied"),
                message="The current operator is not permitted to view this member.",
            ),
        ],
        recovery_rules=[
            RecoveryRule(
                code="session_expired",
                trigger=Locator(strategy=LocatorStrategy.TEST_ID, value="session-expired"),
                action=ActionType.CLICK,
                target=[
                    Locator(
                        strategy=LocatorStrategy.ROLE,
                        value="button",
                        name="Resume session",
                    )
                ],
                message="Resume the expired session",
            ),
            RecoveryRule(
                code="transient_load_error",
                trigger=Locator(
                    strategy=LocatorStrategy.TEST_ID, value="transient-load-error"
                ),
                action=ActionType.CLICK,
                target=[Locator(strategy=LocatorStrategy.ROLE, value="button", name="Retry")],
                message="Retry the transient application error",
            ),
            RecoveryRule(
                code="known_interstitial",
                trigger=Locator(strategy=LocatorStrategy.TEST_ID, value="known-interstitial"),
                action=ActionType.CLICK,
                target=[Locator(strategy=LocatorStrategy.ROLE, value="button", name="Continue")],
                message="Dismiss the known informational interstitial",
            ),
        ],
        success_checkpoint=Locator(
            strategy=LocatorStrategy.TEST_ID, value="member-details-heading"
        ),
    )


def save_artifact(artifact: CapabilityArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
