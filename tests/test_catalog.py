import json
from pathlib import Path
from shutil import copyfile

from fastapi.testclient import TestClient

from banking_gpt.catalog import StabilityStore, create_catalog_app
from banking_gpt.evidence import EvidenceRecorder


def test_catalog_lists_typed_capabilities(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    copyfile(
        "artifacts/lookup-member-profile.json",
        artifact_root / "lookup-member-profile.json",
    )
    client = TestClient(create_catalog_app(artifact_root, tmp_path / "evidence"))
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "lookup-member-profile"
    assert response.json()[0]["inputs"][0]["name"] == "member_id"


def test_catalog_blocks_draft_invocation(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    copyfile(
        "artifacts/read-checking-balance.json",
        artifact_root / "draft-capability.json",
    )
    client = TestClient(create_catalog_app(artifact_root, tmp_path / "evidence"))
    response = client.post(
        "/capabilities/draft-capability/invoke", json={"inputs": {"member_id": "12345"}}
    )
    assert response.status_code == 409


def test_stability_metrics_accumulate(tmp_path: Path) -> None:
    store = StabilityStore(tmp_path / "stability.json")
    store.record("profile", "success", 1)
    store.record("profile", "failure", 0)
    assert store.get("profile") == {
        "runs": 2,
        "successes": 1,
        "business_outcomes": 0,
        "failures": 1,
        "recoveries": 1,
        "success_rate": 0.5,
    }


def test_schema_sensitive_values_are_redacted_from_evidence(tmp_path: Path) -> None:
    recorder = EvidenceRecorder(tmp_path, run_id="run-test")
    recorder.register_sensitive_values(["12345", "$99.00"])
    recorder.event("sample", member_id="12345", balance="$99.00")
    payload = json.loads(recorder.events_path.read_text(encoding="utf-8"))
    assert payload["data"] == {"member_id": "[REDACTED]", "balance": "[REDACTED]"}
