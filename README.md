# BankingGPT

BankingGPT is a small record-once, replay-many computer-use automation system. An LLM can discover a workflow against a live browser, the system compiles the successful actions into a typed capability artifact, and the replay engine runs that artifact deterministically without an LLM deciding the next step.

The included target is a fictional legacy-style bank. It contains synthetic data only.

## Architecture

- **FastAPI + Jinja2** serve the mock bank.
- **Pydantic** defines strict goals, targets, observations, actions, policies, artifacts, outcomes, and interventions.
- **Playwright** implements the browser `SurfaceAdapter` and captures traces/screenshots.
- **ReplayEngine** interprets JSON capability artifacts without a model.
- **DiscoveryEngine** runs the bounded observe-decide-act loop.
- **ScriptedDiscoveryModel** supports offline development; **OllamaDiscoveryModel** performs local LLM discovery.
- **PolicyEngine** applies host/action allowlists and risk approval rules before execution.

## Setup

Requires Python 3.12+, `uv`, and a Chromium-compatible Playwright browser.

```bash
uv sync --extra dev
uv run playwright install chromium
```

Ollama is optional for deterministic replay and required only for a real local LLM discovery run. Install Ollama separately, then pull the tested local model:

```bash
ollama pull gemma4:e2b
```

## Demo path

Start the fictional bank in terminal one:

```bash
uv run banking-gpt mock-bank
```

Validate the supplied artifact:

```bash
uv run banking-gpt validate
```

Run deterministic replay in terminal two:

```bash
uv run banking-gpt replay --member-id 12345
```

## Available capability flows

All capability files are typed, parameterized JSON artifacts executed by the same deterministic replay engine. Each flow accepts a fictional `member_id`, enforces the host/action policy, captures evidence, and returns a structured result.

### 1. Read checking balance

Search for a member and return the checking-account balance:

```bash
uv run banking-gpt replay \
  --artifact artifacts/read-checking-balance.json \
  --member-id 12345
```

Expected outputs:

```json
{"balance": "$1,250.00"}
```

### 2. Look up member profile

Search for a member and return their display name and membership status:

```bash
uv run banking-gpt replay \
  --artifact artifacts/lookup-member-profile.json \
  --member-id 12345
```

Expected outputs:

```json
{"member_name": "Alex Example", "member_status": "Active"}
```

Use member `67890` to demonstrate a different status (`Dormant`). Missing and restricted members still produce the shared `member_not_found` and `permission_denied` business outcomes.

### 3. Read latest transaction

Search for a member, open **Recent Transactions**, and return the latest transaction description and amount:

```bash
uv run banking-gpt replay \
  --artifact artifacts/read-latest-transaction.json \
  --member-id 12345
```

Expected outputs:

```json
{
  "transaction_description": "Payroll deposit",
  "transaction_amount": "+$2,400.00"
}
```

Member `40800` first exercises bounded session-expiry recovery and then returns the expected business outcome `no_recent_transactions` instead of failing.

To watch either new flow, add `--headed --slow-mo-ms 1200 --hold-open-seconds 10` to its replay command.

Watch the browser actions in slow motion:

```bash
uv run banking-gpt replay --headed --slow-mo-ms 1200 --hold-open-seconds 10 --member-id 12345
```

Exercise an expected business outcome:

```bash
uv run banking-gpt replay --member-id 99999
```

Exercise every runtime outcome implemented by the demo:

```bash
# Known business outcomes
uv run banking-gpt replay --member-id 99999  # member_not_found
uv run banking-gpt replay --member-id 40300  # permission_denied

# Recoverable conditions (replay repairs these and continues)
uv run banking-gpt replay --member-id 40800  # session expiry
uv run banking-gpt replay --member-id 50000  # transient load error
uv run banking-gpt replay --member-id 77777  # known interstitial

# Unknown application error (structured hard failure)
uv run banking-gpt replay --member-id 66666
```

Run offline scripted discovery while developing:

```bash
uv run banking-gpt discover --provider scripted --member-id 12345
```

Run genuine local-LLM discovery with an installed Ollama model:

```bash
uv run banking-gpt discover --provider ollama --model gemma4:e2b --member-id 12345
```

The discovery command writes a generated draft artifact to `artifacts/discovered-read-checking-balance.json`. The scripted provider is explicitly a development aid and is not the assignment's required real LLM run. The checked-in `artifacts/ollama-read-checking-balance.json` and `evidence/run-8370ae618658/` were produced by the genuine Ollama-driven run.

Validate or replay that generated artifact with:

```bash
uv run banking-gpt validate --artifact artifacts/discovered-read-checking-balance.json
uv run banking-gpt replay --artifact artifacts/discovered-read-checking-balance.json --member-id 67890
```

To enable same-session human takeover after a replay step becomes stuck:

```bash
uv run banking-gpt replay --artifact artifacts/ollama-read-checking-balance.json \
  --headed --human-on-failure --member-id 66666
```

The automation pauses and leaves the same browser session open. The operator resolves the problem in that window, then presses Enter in the terminal. Replay retries the blocked step, records both ownership transitions, and continues. The checked-in handoff evidence is `evidence/run-a33fd6b0ccae/`.

## Result contract

A replay returns one of:

- `success`: checkpoint verified and declared outputs returned.
- `business_outcome`: the UI returned a known legitimate outcome such as `member_not_found`.
- `failure`: execution could not proceed safely; includes the failed step and evidence path.

## Evidence

Each run creates `evidence/<run-id>/` containing:

- `events.jsonl`: structured, redacted events
- `screenshots/`: step and failure screenshots
- `trace.zip`: Playwright action/DOM/network trace
- `run.json`: final structured replay result

Never use real credentials or personal information in this demonstration.

[`evidence/SUBMISSION.md`](evidence/SUBMISSION.md) is the reviewer index for the genuine discovery, successful replay, business outcomes, recoveries, hard failure, and same-session human handoff. Older local development runs are ignored by Git.

## Tests

```bash
uv run pytest
uv run ruff check .
```

The assignment brief is preserved under [`resources/`](resources/README.md).
