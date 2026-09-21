from pathlib import Path

import pytest
from pydantic import ValidationError

from banking_gpt.models import ActionType, ProposedAction
from banking_gpt.replay import load_artifact


def test_fill_requires_target_and_value() -> None:
    with pytest.raises(ValidationError):
        ProposedAction(action=ActionType.FILL, explanation="Fill a field")


def test_complete_requires_no_target() -> None:
    action = ProposedAction(
        action=ActionType.COMPLETE,
        target=[],
        value=None,
        output_name=None,
        explanation="Goal is complete",
    )
    assert action.target == []


@pytest.mark.parametrize(
    ("filename", "expected_outputs"),
    [
        ("lookup-member-profile.json", {"member_name", "member_status"}),
        (
            "read-latest-transaction.json",
            {"transaction_description", "transaction_amount"},
        ),
    ],
)
def test_additional_capability_artifacts_are_valid(
    filename: str, expected_outputs: set[str]
) -> None:
    artifact = load_artifact(Path("artifacts") / filename)
    assert artifact.approval_status == "approved"
    assert {output.name for output in artifact.outputs} == expected_outputs
