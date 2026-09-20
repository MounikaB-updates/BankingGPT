# 1. Architecture

The system is a modular Python application with domain contracts separated from infrastructure. A `SurfaceAdapter` defines observation and action operations; Playwright is the first concrete adapter. Discovery and deterministic replay share this adapter but differ in decision-making: an LLM proposes discovery actions, while replay interprets a validated artifact. FastAPI/Jinja2 provide a safe local legacy-style target. JSON/JSONL keeps the take-home implementation reviewable and avoids premature database or queue infrastructure.

# 2. Artifact schema

`CapabilityArtifact` is a strict, versioned Pydantic contract containing identity, typed inputs and outputs, application compatibility, allowed hosts, ordered steps, ranked locator candidates, retry policies, known business outcomes, a success checkpoint, and approval status. Invocation values use explicit placeholders such as `{{member_id}}`; raw discovery transcripts are not artifacts. Generated artifacts remain drafts until reviewed.

# 3. Determinism & error handling

Replay never invokes a model. It validates the artifact and inputs, interpolates parameters, policy-checks every step, resolves locators by priority, performs bounded retries, extracts declared outputs, and verifies the final checkpoint. Accessibility labels and roles are preferred, followed by test IDs and narrow CSS fallbacks. Results distinguish success, known business outcomes, recoverable conditions, and hard failures. The demo detects member-not-found and permission-denied as business outcomes; session expiry, a transient load error, and a known interstitial are repaired by typed, bounded recovery rules; an unknown application error stops with step-level evidence. Missing or ambiguous targets, policy violations, and checkpoint failures also stop safely.

# 4. Heterogeneity & multi-tenant

Browser-specific behavior is behind `SurfaceAdapter`; a desktop accessibility or screenshot/coordinate adapter can implement the same observation/action contract. Artifacts express semantic actions and surface-neutral workflow data, with surface-specific locator strategies kept as typed values. At scale, artifacts would identify a vendor product and compatible versions, while tenant profiles would supply entry points, branding metadata, and narrow locator overrides. Compatibility probes and replay health would gate unattended execution.

# 5. Escalation & handoff

Failures can emit an `InterventionRequest` containing run, capability, step, reason, and screenshot. The minimal real handoff retains the same headed Playwright context, changes explicit ownership from automation to human, lets the operator act in the live browser, records the start and end of the handoff, and retries the blocked step after confirmation. Evidence run `run-a33fd6b0ccae` demonstrates this: replay hit an unknown app error, the human navigated the same browser session to the correct member, and extraction resumed successfully. A production console would replace terminal confirmation with authenticated leases, identity-attributed manual action capture, and streamed session access.

# 6. Safety

The policy engine enforces allowed hosts and actions before execution, limits steps and time, and requires approval for irreversible actions. Pydantic rejects malformed model actions. Logs apply basic token/secret/identifier redaction, artifacts parameterize invocation values, and all included records are fictional. Production use would require institution-specific data classification, encryption, identity, retention, and audit controls beyond this demo.

# 7. Cuts

The project deliberately uses one browser surface, one read-only workflow, local files, and a minimal manual-control seam. It does not implement production authentication, encrypted storage, distributed scheduling, full desktop automation, a polished operator console, tenant administration, or automatic artifact approval. The mock operator flow records ownership transitions but not every low-level manual click. Next steps would deepen locator scoring and artifact review, add authenticated human action auditing, implement tenant overrides, and evaluate replay stability across repeated runs.
