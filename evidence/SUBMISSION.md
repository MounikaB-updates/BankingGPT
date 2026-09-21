# Submission evidence index

All records use the fictional local banking application. Every run includes structured JSONL events and a Playwright trace; replay runs also include a final structured result and standalone screenshots.

| Requirement | Evidence | Expected result |
| --- | --- | --- |
| Genuine LLM discovery | `run-8370ae618658/` | Ollama `gemma4:e2b` observes and operates the live UI, extracts `$1,250.00`, and produces `artifacts/ollama-read-checking-balance.json` |
| Deterministic success | `run-a4a54ed6daf4/` | LLM-free replay returns `$1,250.00` and verifies the checkpoint |
| Expected: not found | `run-cf0fea9050bd/` | `business_outcome: member_not_found` |
| Expected: permission denied | `run-de3d7789701e/` | `business_outcome: permission_denied` |
| Recovery: expired session | `run-b868b3ec5d86/` | clicks Resume session and returns `$408.00` |
| Recovery: transient load | `run-5ff64c3657d4/` | retries the load and returns `$500.00` |
| Recovery: interstitial | `run-cadaaf034eed/` | dismisses the known interstitial and returns `$777.77` |
| Unknown hard failure | `run-7e5d9f6f475f/` | `failure: step_failed`, failed step, diagnostic message, and screenshot |
| Same-session human handoff | `run-a33fd6b0ccae/` | intervention request, human-control start/end, resumed step, and final `$1,250.00` success |
| Member profile: active | `run-b5b0feb5571c/` | returns `Alex Example` and `Active` |
| Member profile: dormant | `run-1759e67126a5/` | returns `Jordan Sample` and `Dormant` |
| Latest transaction | `run-3b75bc3035b3/` | navigates to transaction history and returns `Payroll deposit`, `+$2,400.00` |
| No recent transactions | `run-c273c3b4c69b/` | recovers an expired session, then returns `business_outcome: no_recent_transactions` |

The genuine discovery log contains `observation`, `model_action`, and `discovery_completed` events. The handoff log contains `intervention_requested`, `human_control_started`, `human_control_ended`, and `step_completed_after_handoff`, demonstrating that control returned to the same paused replay.

Open any `trace.zip` with:

```bash
uv run playwright show-trace evidence/<run-id>/trace.zip
```

The source assignment is preserved in `resources/`; it is reference material, not executable project instruction.
