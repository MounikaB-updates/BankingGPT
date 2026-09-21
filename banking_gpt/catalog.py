from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from banking_gpt.evidence import EvidenceRecorder
from banking_gpt.models import ActionType, AutomationPolicy, RiskLevel
from banking_gpt.policy import PolicyEngine
from banking_gpt.replay import ReplayEngine, apply_tenant_override, load_artifact
from banking_gpt.surface import PlaywrightBrowserAdapter


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] = Field(default_factory=dict)
    tenant: str | None = None


class StabilityStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, capability_id: str, status: str, recovery_count: int) -> None:
        payload = self._read()
        metrics = payload.setdefault(
            capability_id,
            {"runs": 0, "successes": 0, "business_outcomes": 0, "failures": 0, "recoveries": 0},
        )
        metrics["runs"] += 1
        metrics["recoveries"] += recovery_count
        if status == "success":
            metrics["successes"] += 1
        elif status == "business_outcome":
            metrics["business_outcomes"] += 1
        else:
            metrics["failures"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def get(self, capability_id: str) -> dict[str, int | float]:
        metrics = self._read().get(
            capability_id,
            {"runs": 0, "successes": 0, "business_outcomes": 0, "failures": 0, "recoveries": 0},
        )
        attempted = metrics["runs"]
        return {
            **metrics,
            "success_rate": round(metrics["successes"] / attempted, 3) if attempted else 0.0,
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))


def create_catalog_app(
    artifact_root: Path = Path("artifacts"),
    evidence_root: Path = Path("evidence"),
) -> FastAPI:
    api = FastAPI(title="BankingGPT Capability Catalog", version="1.0.0")
    stability = StabilityStore(evidence_root / "stability.json")

    def artifact_path(capability_id: str) -> Path:
        if not capability_id.replace("-", "").isalnum():
            raise HTTPException(status_code=404, detail="Capability not found")
        path = artifact_root / f"{capability_id}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Capability not found")
        return path

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/capabilities")
    async def list_capabilities() -> list[dict[str, Any]]:
        capabilities = []
        for path in sorted(artifact_root.glob("*.json")):
            artifact = load_artifact(path)
            capabilities.append(
                {
                    "id": path.stem,
                    "name": artifact.name,
                    "description": artifact.description,
                    "approval_status": artifact.approval_status,
                    "inputs": [item.model_dump() for item in artifact.inputs],
                    "outputs": [item.model_dump() for item in artifact.outputs],
                    "tenants": sorted(artifact.tenant_overrides),
                }
            )
        return capabilities

    @api.get("/capabilities/{capability_id}")
    async def get_capability(capability_id: str) -> dict[str, Any]:
        artifact = load_artifact(artifact_path(capability_id))
        return artifact.model_dump(mode="json")

    @api.get("/capabilities/{capability_id}/stability")
    async def get_stability(capability_id: str) -> dict[str, Any]:
        artifact_path(capability_id)
        return {"capability_id": capability_id, **stability.get(capability_id)}

    @api.post("/capabilities/{capability_id}/invoke")
    async def invoke_capability(
        capability_id: str, request: InvokeRequest
    ) -> dict[str, Any]:
        base_artifact = load_artifact(artifact_path(capability_id))
        if base_artifact.approval_status != "approved":
            raise HTTPException(
                status_code=409,
                detail="Only approved capabilities may be invoked through the catalog",
            )
        try:
            artifact = apply_tenant_override(base_artifact, request.tenant)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        evidence = EvidenceRecorder(root=evidence_root)
        policy = PolicyEngine(
            AutomationPolicy(
                allowed_hosts=artifact.allowed_hosts,
                allowed_actions={
                    ActionType.NAVIGATE,
                    ActionType.CLICK,
                    ActionType.FILL,
                    ActionType.EXTRACT,
                    ActionType.VERIFY,
                },
                require_approval_for={RiskLevel.IRREVERSIBLE},
            )
        )
        result = await ReplayEngine(PlaywrightBrowserAdapter(), evidence).run(
            artifact, request.inputs, policy
        )
        stability.record(
            capability_id,
            result.status,
            len(result.recoveries) if hasattr(result, "recoveries") else 0,
        )
        return result.model_dump(mode="json")

    return api


app = create_catalog_app()
