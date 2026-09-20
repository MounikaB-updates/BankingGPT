# Evidence

Runtime evidence is created in a separate `run-<id>/` directory by discovery and replay commands. A final submission should preserve:

1. One genuine Ollama-driven discovery run
2. The generated capability artifact
3. One successful deterministic replay
4. One replay with a known business outcome or injected failure
5. Screenshots and Playwright traces for those runs

Scripted-provider runs are development evidence only and do not satisfy the assignment's real LLM requirement.

## Curated submission evidence

See [`SUBMISSION.md`](SUBMISSION.md) for the verified run IDs and the complete requirement-to-evidence matrix. The generated capability is `artifacts/ollama-read-checking-balance.json`.
