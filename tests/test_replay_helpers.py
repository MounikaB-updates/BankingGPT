import pytest

from banking_gpt.replay import render_parameters


def test_renders_artifact_parameters() -> None:
    assert render_parameters("member={{member_id}}", {"member_id": "12345"}) == "member=12345"


def test_missing_parameter_fails() -> None:
    with pytest.raises(ValueError, match="Missing required input"):
        render_parameters("{{member_id}}", {})

