from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
import uvicorn

from banking_gpt.discovery import DiscoveryEngine, compile_balance_artifact, save_artifact
from banking_gpt.evidence import EvidenceRecorder
from banking_gpt.handoff import HandoffCoordinator
from banking_gpt.mock_bank import app as mock_bank_app
from banking_gpt.models import ActionType, AutomationPolicy, Goal, RiskLevel, SurfaceType, Target
from banking_gpt.policy import PolicyEngine
from banking_gpt.providers import OllamaDiscoveryModel, ScriptedDiscoveryModel
from banking_gpt.replay import ReplayEngine, load_artifact
from banking_gpt.surface import PlaywrightBrowserAdapter

app = typer.Typer(help="Computer-use discovery and deterministic replay demo.")


def default_policy(hosts: list[str]) -> AutomationPolicy:
    return AutomationPolicy(
        allowed_hosts=hosts,
        allowed_actions={
            ActionType.NAVIGATE,
            ActionType.CLICK,
            ActionType.FILL,
            ActionType.EXTRACT,
            ActionType.VERIFY,
            ActionType.COMPLETE,
            ActionType.REQUEST_HELP,
        },
        max_steps=20,
        timeout_seconds=120,
        require_approval_for={RiskLevel.IRREVERSIBLE},
    )


@app.command("mock-bank")
def mock_bank(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the fictional legacy banking target."""
    uvicorn.run(mock_bank_app, host=host, port=port)


@app.command()
def validate(artifact: Path = Path("artifacts/read-checking-balance.json")) -> None:
    """Validate and summarize a capability artifact."""
    capability = load_artifact(artifact)
    typer.echo(
        json.dumps(
            {
                "valid": True,
                "name": capability.name,
                "version": capability.artifact_version,
                "steps": len(capability.steps),
            },
            indent=2,
        )
    )


@app.command()
def replay(
    artifact: Path = Path("artifacts/read-checking-balance.json"),
    member_id: Annotated[str, typer.Option(help="Fictional member identifier")] = "12345",
    headed: bool = False,
    slow_mo_ms: Annotated[
        int, typer.Option(help="Delay each browser action so it is easier to watch")
    ] = 0,
    hold_open_seconds: Annotated[
        float, typer.Option(help="Keep the completed browser visible before closing")
    ] = 0,
    human_on_failure: Annotated[
        bool, typer.Option(help="Pause for manual control in the same headed browser")
    ] = False,
) -> None:
    """Run a saved capability without an LLM."""
    capability = load_artifact(artifact)
    evidence = EvidenceRecorder()
    surface = PlaywrightBrowserAdapter(
        headless=not headed,
        slow_mo_ms=slow_mo_ms,
        close_delay_seconds=hold_open_seconds,
    )
    engine = ReplayEngine(surface, evidence)
    policy = PolicyEngine(default_policy(capability.allowed_hosts))
    if human_on_failure and not headed:
        raise typer.BadParameter("--human-on-failure requires --headed")
    handoff = HandoffCoordinator() if human_on_failure else None
    result = asyncio.run(
        engine.run(capability, {"member_id": member_id}, policy, handoff=handoff)
    )
    typer.echo(result.model_dump_json(indent=2))
    raise typer.Exit(code=0 if result.status != "failure" else 1)


@app.command()
def discover(
    goal: str = "Look up member 12345 and return the checking balance",
    target_url: str = "http://127.0.0.1:8000/",
    provider: Annotated[str, typer.Option(help="scripted or ollama")] = "scripted",
    model: Annotated[str, typer.Option(help="Installed Ollama model name")] = "",
    member_id: str = "12345",
    headed: bool = True,
    output: Path = Path("artifacts/discovered-read-checking-balance.json"),
) -> None:
    """Run an observe-decide-act discovery session."""
    if provider == "ollama" and not model:
        raise typer.BadParameter("--model is required when --provider ollama is selected")
    if provider not in {"scripted", "ollama"}:
        raise typer.BadParameter("provider must be scripted or ollama")
    hostname = urlparse(target_url).hostname
    if not hostname:
        raise typer.BadParameter("target-url must be an absolute URL")
    discovery_model = (
        OllamaDiscoveryModel(model)
        if provider == "ollama"
        else ScriptedDiscoveryModel(member_id)
    )
    evidence = EvidenceRecorder()
    engine = DiscoveryEngine(
        surface=PlaywrightBrowserAdapter(headless=not headed),
        model=discovery_model,
        evidence=evidence,
        policy=default_policy([hostname]),
    )
    actions = asyncio.run(
        engine.run(
            Goal(description=goal),
            Target(
                surface_type=SurfaceType.BROWSER,
                application="mock-bank",
                entry_point=target_url,
            ),
        )
    )
    artifact = compile_balance_artifact(
        actions, member_id=member_id, entry_point=target_url
    )
    save_artifact(artifact, output)
    typer.echo(json.dumps([item.model_dump(mode="json") for item in actions], indent=2))
    typer.echo(f"Artifact: {output}")
    typer.echo(f"Evidence: {evidence.directory}")


if __name__ == "__main__":
    app()
