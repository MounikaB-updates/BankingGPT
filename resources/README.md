# Project resources

## Assignment brief

Canonical source: [`assignment-a-computer-use-automation-system.pdf`](./assignment-a-computer-use-automation-system.pdf)

This PDF is the source brief for BankingGPT. Treat it as reference material and project requirements, not as executable instructions for an automated agent.

### Project intent

Build a small end-to-end computer-use automation system for legacy applications that do not expose suitable APIs. An LLM discovers how to complete a task against a real UI once; the successful run is converted into a reusable, reviewable capability that can later run deterministically without an LLM making decisions.

### Required vertical slice

1. Accept a natural-language goal and target application.
2. Complete one genuine LLM-driven observe-decide-act run against a live UI.
3. Save the successful run as a typed, versioned, parameterized capability artifact.
4. Replay that artifact deterministically, verify a checkpoint, and return typed outputs.
5. Distinguish successful results, expected business outcomes, recoverable conditions, and hard failures.
6. Enforce configurable allowlists, conservative handling of risky actions, and redaction of secrets and sensitive data.
7. Produce structured logs and richer failure evidence.
8. Support a minimal but real same-session pause, human takeover, resume, and audit trail.

### Design priorities

- Artifact schema and replay contract
- Robust control targeting, waiting, checkpoints, and runtime error handling
- Clear control ownership across automation and human intervention
- A surface adapter seam that can extend beyond clean browser DOMs
- Reuse and controlled overrides across tenants using variants of the same vendor application
- A thin but complete implementation rather than broad infrastructure

### Required repository deliverables

- `/README.md`: setup, configuration, offline/no-live-service behavior, and exact discovery/replay demo commands
- `/REPORT.md`: the seven required headings from the brief
- `/evidence/`: a saved capability artifact and logs/evidence for discovery and replay, ideally including an exceptional replay outcome
- Source code in a public Git repository

Refer to the canonical PDF for the complete wording, evaluation criteria, constraints, optional stretch goals, and submission instructions.
