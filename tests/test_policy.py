import pytest

from banking_gpt.cli import default_policy
from banking_gpt.models import ActionType, ArtifactStep, ProposedAction, RiskLevel
from banking_gpt.policy import (
    PolicyApprovalRequired,
    PolicyEngine,
    PolicyViolation,
    redact,
)


def test_blocks_external_navigation() -> None:
    policy = PolicyEngine(default_policy(["localhost"]))
    action = ProposedAction(
        action=ActionType.NAVIGATE,
        target=[],
        value="https://example.com",
        output_name=None,
        explanation="Leave the permitted application",
    )
    with pytest.raises(PolicyViolation):
        policy.check_action(action)


def test_redacts_secrets_and_nine_digit_identifiers() -> None:
    assert "secret-value" not in redact("token=secret-value")
    assert "123456789" not in redact("SSN 123456789")


def test_irreversible_step_requires_human_approval() -> None:
    policy = PolicyEngine(default_policy(["localhost"]))
    step = ArtifactStep(
        id="submit-transfer",
        action=ActionType.CLICK,
        risk=RiskLevel.IRREVERSIBLE,
        description="Submit an irreversible transfer",
    )
    with pytest.raises(PolicyApprovalRequired):
        policy.check_step(step)
