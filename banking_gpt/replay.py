from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from banking_gpt.evidence import EvidenceRecorder
from banking_gpt.handoff import HandoffCoordinator
from banking_gpt.models import (
    ArtifactStep,
    BusinessOutcomeResult,
    CapabilityArtifact,
    FailureResult,
    InterventionReason,
    InterventionRequest,
    ProposedAction,
    RecoveryRecord,
    SuccessResult,
    Target,
)
from banking_gpt.policy import PolicyApprovalRequired, PolicyEngine, PolicyViolation
from banking_gpt.surface import PlaywrightBrowserAdapter, SurfaceAdapter, SurfaceError

_PARAMETER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_parameters(value: str | None, inputs: dict[str, Any]) -> str | None:
    if value is None:
        return None

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in inputs:
            raise ValueError(f"Missing required input: {key}")
        return str(inputs[key])

    return _PARAMETER.sub(replace, value)


def apply_tenant_override(
    artifact: CapabilityArtifact, tenant: str | None
) -> CapabilityArtifact:
    capability = deepcopy(artifact)
    if not tenant:
        return capability
    override = capability.tenant_overrides.get(tenant)
    if override is None:
        raise ValueError(f"Unknown tenant override: {tenant}")
    if override.entry_point:
        capability.entry_point = override.entry_point
    if override.success_checkpoint:
        capability.success_checkpoint = override.success_checkpoint
    for step in capability.steps:
        if step.id in override.step_locators:
            step.target = override.step_locators[step.id]
    return capability


class ReplayEngine:
    def __init__(self, surface: SurfaceAdapter, evidence: EvidenceRecorder) -> None:
        self.surface = surface
        self.evidence = evidence

    async def run(
        self,
        artifact: CapabilityArtifact,
        inputs: dict[str, Any],
        policy: PolicyEngine,
        handoff: HandoffCoordinator | None = None,
    ) -> SuccessResult | BusinessOutcomeResult | FailureResult:
        outputs: dict[str, Any] = {}
        recoveries: list[RecoveryRecord] = []
        target = Target(
            surface_type=artifact.surface_type,
            application=artifact.application,
            entry_point=artifact.entry_point,
        )
        self._validate_inputs(artifact, inputs)
        self.evidence.register_sensitive_values(
            inputs[item.name]
            for item in artifact.inputs
            if item.sensitive and item.name in inputs
        )
        self.evidence.event("replay_started", capability=artifact.name)
        await self.surface.start(target)

        try:
            for index, step in enumerate(artifact.steps):
                if index >= policy.policy.max_steps:
                    return await self._failure("max_steps", "Maximum steps exceeded", step.id)

                outcome = await self._detect_business_outcome(artifact)
                if outcome:
                    self.evidence.save_result(outcome)
                    return outcome

                recovery_failure = await self._recover_known_conditions(
                    artifact, step.id, recoveries
                )
                if recovery_failure:
                    return recovery_failure

                try:
                    policy.check_step(step)
                except PolicyApprovalRequired as exc:
                    return await self._failure(
                        "approval_required", str(exc), step.id, can_intervene=True
                    )

                action = self._step_to_action(step, inputs)
                self.evidence.event(
                    "step_started", step_id=step.id, action=action.model_dump(mode="json")
                )

                last_error: Exception | None = None
                for attempt in range(1, step.retry.max_attempts + 1):
                    try:
                        value = await self.surface.execute(action)
                        if step.output_name:
                            self._capture_output(artifact, outputs, step, value)
                        screenshot = self.evidence.screenshot_path(
                            f"step-{index + 1:02d}-{step.id}"
                        )
                        await self.surface.capture_screenshot(screenshot)
                        self.evidence.event("step_completed", step_id=step.id, attempt=attempt)
                        last_error = None
                        break
                    except SurfaceError as exc:
                        last_error = exc
                        if attempt < step.retry.max_attempts:
                            recoveries.append(
                                RecoveryRecord(
                                    step_id=step.id, attempt=attempt, reason=str(exc)
                                )
                            )
                            self.evidence.event(
                                "step_retry", step_id=step.id, attempt=attempt, reason=str(exc)
                            )
                            await asyncio.sleep(step.retry.delay_seconds)

                if last_error:
                    recovery_failure = await self._recover_known_conditions(
                        artifact, step.id, recoveries
                    )
                    if recovery_failure:
                        return recovery_failure
                    if recoveries:
                        try:
                            value = await self.surface.execute(action)
                            if step.output_name:
                                self._capture_output(artifact, outputs, step, value)
                            screenshot = self.evidence.screenshot_path(
                                f"step-{index + 1:02d}-{step.id}-after-recovery"
                            )
                            await self.surface.capture_screenshot(screenshot)
                            self.evidence.event("step_completed_after_recovery", step_id=step.id)
                            continue
                        except SurfaceError as exc:
                            last_error = exc
                    outcome = await self._detect_business_outcome(artifact)
                    if outcome:
                        self.evidence.save_result(outcome)
                        return outcome
                    if handoff and isinstance(self.surface, PlaywrightBrowserAdapter):
                        request = InterventionRequest(
                            id=f"intervention-{uuid4().hex[:8]}",
                            run_id=self.evidence.run_id,
                            capability=artifact.name,
                            step_id=step.id,
                            reason=InterventionReason.STUCK,
                            message=str(last_error),
                            screenshot_path=str(self.evidence.screenshot_path("intervention")),
                        )
                        await self.surface.capture_screenshot(Path(request.screenshot_path))
                        self.evidence.event(
                            "intervention_requested", request=request.model_dump(mode="json")
                        )
                        await handoff.hand_to_human(request, self.surface, self.evidence)
                        try:
                            value = await self.surface.execute(action)
                            if step.output_name:
                                self._capture_output(artifact, outputs, step, value)
                            screenshot = self.evidence.screenshot_path(
                                f"step-{index + 1:02d}-{step.id}-after-handoff"
                            )
                            await self.surface.capture_screenshot(screenshot)
                            self.evidence.event("step_completed_after_handoff", step_id=step.id)
                            continue
                        except SurfaceError as exc:
                            last_error = exc
                    return await self._failure(
                        "step_failed", str(last_error), step.id, can_intervene=True
                    )

            if not await self.surface.is_visible(artifact.success_checkpoint, timeout_ms=2_000):
                return await self._failure(
                    "checkpoint_failed",
                    "The final success checkpoint was not visible",
                    artifact.steps[-1].id if artifact.steps else None,
                    can_intervene=True,
                )

            result = SuccessResult(
                run_id=self.evidence.run_id, outputs=outputs, recoveries=recoveries
            )
            final_screenshot = self.evidence.screenshot_path("completed")
            await self.surface.capture_screenshot(final_screenshot)
            self.evidence.event("replay_completed", outputs=outputs)
            self.evidence.save_result(result)
            return result
        except (PolicyViolation, ValueError) as exc:
            return await self._failure("validation_or_policy", str(exc), None)
        except Exception as exc:  # boundary: always return a structured failure
            return await self._failure("unexpected_error", str(exc), None, can_intervene=True)
        finally:
            await self.surface.close(self.evidence.trace_path())

    def _validate_inputs(self, artifact: CapabilityArtifact, inputs: dict[str, Any]) -> None:
        required = {item.name for item in artifact.inputs if item.required}
        missing = required - inputs.keys()
        unknown = inputs.keys() - {item.name for item in artifact.inputs}
        if missing:
            raise ValueError(f"Missing inputs: {sorted(missing)}")
        if unknown:
            raise ValueError(f"Unknown inputs: {sorted(unknown)}")

    def _step_to_action(self, step: ArtifactStep, inputs: dict[str, Any]) -> ProposedAction:
        return ProposedAction(
            action=step.action,
            target=step.target,
            value=render_parameters(step.value, inputs),
            output_name=step.output_name,
            explanation=step.description,
        )

    def _capture_output(
        self,
        artifact: CapabilityArtifact,
        outputs: dict[str, Any],
        step: ArtifactStep,
        value: Any,
    ) -> None:
        if not step.output_name:
            return
        outputs[step.output_name] = value
        if any(
            item.name == step.output_name and item.sensitive
            for item in artifact.outputs
        ):
            self.evidence.register_sensitive_values([value])

    async def _detect_business_outcome(
        self, artifact: CapabilityArtifact
    ) -> BusinessOutcomeResult | None:
        for rule in artifact.business_outcomes:
            if await self.surface.is_visible(rule.locator):
                return BusinessOutcomeResult(
                    run_id=self.evidence.run_id, code=rule.code, message=rule.message
                )
        return None

    async def _recover_known_conditions(
        self,
        artifact: CapabilityArtifact,
        step_id: str,
        recoveries: list[RecoveryRecord],
    ) -> FailureResult | None:
        for rule in artifact.recovery_rules:
            if not await self.surface.is_visible(rule.trigger):
                continue
            for attempt in range(1, rule.max_attempts + 1):
                self.evidence.event(
                    "recovery_started", code=rule.code, step_id=step_id, attempt=attempt
                )
                try:
                    await self.surface.execute(
                        ProposedAction(
                            action=rule.action,
                            target=rule.target,
                            value=None,
                            output_name=None,
                            explanation=rule.message,
                        )
                    )
                    recoveries.append(
                        RecoveryRecord(step_id=step_id, attempt=attempt, reason=rule.code)
                    )
                    screenshot = self.evidence.screenshot_path(f"recovered-{rule.code}")
                    await self.surface.capture_screenshot(screenshot)
                    self.evidence.event(
                        "recovery_completed", code=rule.code, step_id=step_id
                    )
                    return None
                except SurfaceError as exc:
                    if attempt == rule.max_attempts:
                        return await self._failure(
                            "recovery_exhausted", str(exc), step_id, can_intervene=True
                        )
        return None

    async def _failure(
        self,
        code: str,
        message: str,
        step_id: str | None,
        *,
        can_intervene: bool = False,
    ) -> FailureResult:
        path = self.evidence.screenshot_path("failure")
        try:
            await self.surface.capture_screenshot(path)
        except Exception:
            pass
        result = FailureResult(
            run_id=self.evidence.run_id,
            code=code,
            message=message,
            failed_step=step_id,
            evidence={"screenshot": str(path)},
            can_intervene=can_intervene,
        )
        self.evidence.event("replay_failed", result=result.model_dump(mode="json"))
        self.evidence.save_result(result)
        return result


def load_artifact(path: Path) -> CapabilityArtifact:
    return CapabilityArtifact.model_validate_json(path.read_text(encoding="utf-8"))
