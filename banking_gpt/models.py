from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SurfaceType(StrEnum):
    BROWSER = "browser"
    DESKTOP = "desktop"


class ActionType(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    VERIFY = "verify"
    COMPLETE = "complete"
    REQUEST_HELP = "request_help"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class Goal(StrictModel):
    description: str = Field(min_length=3)


class Target(StrictModel):
    surface_type: SurfaceType
    application: str
    entry_point: HttpUrl


class LocatorStrategy(StrEnum):
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    TEST_ID = "test_id"
    CSS = "css"


class Locator(StrictModel):
    strategy: LocatorStrategy
    value: str
    name: str | None = None
    exact: bool = True
    priority: int = Field(default=1, ge=1)
    frame: str | None = None


class InteractiveElement(StrictModel):
    role: str
    name: str
    element_id: str | None = None


class Observation(StrictModel):
    url: str
    title: str
    visible_text: str
    elements: list[InteractiveElement]
    screenshot_path: str | None = None


class ProposedAction(StrictModel):
    action: ActionType
    target: list[Locator]
    value: str | None
    output_name: str | None
    explanation: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_action_fields(self) -> ProposedAction:
        targeted = {ActionType.CLICK, ActionType.FILL, ActionType.EXTRACT, ActionType.VERIFY}
        if self.action in targeted and not self.target:
            raise ValueError(f"{self.action} requires at least one locator")
        if self.action in {ActionType.FILL, ActionType.NAVIGATE} and self.value is None:
            raise ValueError(f"{self.action} requires a value")
        if self.action == ActionType.EXTRACT and not self.output_name:
            raise ValueError("extract requires output_name")
        return self


class InputDefinition(StrictModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"]
    description: str
    required: bool = True
    sensitive: bool = False


class OutputDefinition(StrictModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"]
    description: str
    sensitive: bool = False


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    delay_seconds: float = Field(default=0.25, ge=0, le=10)


class ArtifactStep(StrictModel):
    id: str
    action: ActionType
    target: list[Locator] = Field(default_factory=list)
    value: str | None = None
    output_name: str | None = None
    risk: RiskLevel = RiskLevel.READ_ONLY
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    description: str


class OutcomeRule(StrictModel):
    code: str
    locator: Locator
    message: str


class RecoveryRule(StrictModel):
    code: str
    trigger: Locator
    action: ActionType
    target: list[Locator]
    message: str
    max_attempts: int = Field(default=1, ge=1, le=3)


class TenantOverride(StrictModel):
    entry_point: str | None = None
    step_locators: dict[str, list[Locator]] = Field(default_factory=dict)
    success_checkpoint: Locator | None = None


class CapabilityArtifact(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    artifact_version: str = "1.0.0"
    name: str
    description: str
    application: str
    surface_type: SurfaceType
    entry_point: str
    inputs: list[InputDefinition]
    outputs: list[OutputDefinition]
    allowed_hosts: list[str]
    steps: list[ArtifactStep]
    business_outcomes: list[OutcomeRule] = Field(default_factory=list)
    recovery_rules: list[RecoveryRule] = Field(default_factory=list)
    success_checkpoint: Locator
    tenant_overrides: dict[str, TenantOverride] = Field(default_factory=dict)
    approval_status: Literal["draft", "under_review", "approved", "deprecated"] = "draft"


class AutomationPolicy(StrictModel):
    allowed_hosts: list[str]
    allowed_actions: set[ActionType]
    max_steps: int = Field(default=20, ge=1, le=100)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    require_approval_for: set[RiskLevel] = Field(
        default_factory=lambda: {RiskLevel.IRREVERSIBLE}
    )


class RecoveryRecord(StrictModel):
    step_id: str
    attempt: int
    reason: str


class SuccessResult(StrictModel):
    status: Literal["success"] = "success"
    run_id: str
    outputs: dict[str, Any]
    recoveries: list[RecoveryRecord] = Field(default_factory=list)


class BusinessOutcomeResult(StrictModel):
    status: Literal["business_outcome"] = "business_outcome"
    run_id: str
    code: str
    message: str


class FailureResult(StrictModel):
    status: Literal["failure"] = "failure"
    run_id: str
    code: str
    message: str
    failed_step: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    can_intervene: bool = False


RunResult = Annotated[
    SuccessResult | BusinessOutcomeResult | FailureResult,
    Field(discriminator="status"),
]


class InterventionReason(StrEnum):
    STUCK = "stuck"
    POLICY_APPROVAL = "policy_approval"
    UNEXPECTED_STATE = "unexpected_state"


class InterventionRequest(StrictModel):
    id: str
    run_id: str
    capability: str
    step_id: str | None
    reason: InterventionReason
    message: str
    screenshot_path: str | None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
