# Marketplace Phase 1 Progress

## Completed in batch 1 (tickets #12-#14)

### #12 Repo split scaffold (non-breaking)
- Added scaffold directories:
  - `packages/core`
  - `packages/local-cli`
  - `packages/github-runtime`
- Added README stubs in each package describing intended responsibility.
- Existing root Python package/CLI layout remains unchanged and continues to pass all tests.

### #13 GitHub Action MVP
- Added composite action: `actions/setup/action.yml`
  - Installs `agentplan` with `pip`.
  - Validates resolved version (if `version` input provided).
  - Exposes output: `agentplan-version`.
- Added composite action: `actions/run-chain/action.yml`
  - Inputs: `project-slug`, `max-tickets`, `timeout`.
  - Runs chain command in forced CI/headless mode.
  - Emits output: `chain-status`.
  - Writes run details to `$GITHUB_STEP_SUMMARY`.
- Added docs: `docs/marketplace/quickstart.md` with setup and run-chain examples.

### #14 Runner mode (headless)
- Added CI detection via env flag `AGENTPLAN_CI` (`1/true/yes/on`).
- Added non-interactive subprocess path for:
  - `agentplan chain ...`
  - `agentplan context <project>` (project-mode generation)
- In CI mode, `spawn_terminal` is not used.
- Existing local behavior remains unchanged when `AGENTPLAN_CI` is not set.

## Tests completed
- Added tests for:
  - CI/headless path for `context` and `chain`.
  - Marketplace action contract assumptions (`setup` and `run-chain` YAMLs).
- Full suite run:
  - `pytest test_agentplan.py -v`
  - Result: `229 passed`.

## Remaining for Phase 1 (outside this batch)
- No additional items from tickets #12-#14 remain in this batch.
- Future marketplace-phase scope (beyond #14) should proceed in subsequent execution batches.
