from pathlib import Path

import pytest

from banking_gpt.replay import apply_tenant_override, load_artifact, render_parameters


def test_renders_artifact_parameters() -> None:
    assert render_parameters("member={{member_id}}", {"member_id": "12345"}) == "member=12345"


def test_missing_parameter_fails() -> None:
    with pytest.raises(ValueError, match="Missing required input"):
        render_parameters("{{member_id}}", {})


def test_tenant_override_changes_entry_point_and_frame_locators() -> None:
    artifact = load_artifact(Path("artifacts/read-checking-balance-legacy-iframe.json"))
    harbor = apply_tenant_override(artifact, "harbor")
    assert harbor.entry_point.endswith("/legacy/harbor")
    assert harbor.steps[0].target[0].frame == "#banking-workspace"
    assert artifact.steps[0].target[0].frame == "#core-frame"


def test_unknown_tenant_override_fails() -> None:
    artifact = load_artifact(Path("artifacts/read-checking-balance-legacy-iframe.json"))
    with pytest.raises(ValueError, match="Unknown tenant"):
        apply_tenant_override(artifact, "missing")
