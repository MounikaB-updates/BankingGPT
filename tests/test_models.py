import pytest
from pydantic import ValidationError

from banking_gpt.models import ActionType, ProposedAction


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
