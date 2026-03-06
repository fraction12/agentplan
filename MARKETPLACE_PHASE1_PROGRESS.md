# Marketplace Phase 1 Progress

## Completed
- [x] #12 Repo split scaffold (non-breaking)
- [x] #13 GitHub Action MVP
- [x] #14 Runner mode (headless)
- [x] #15 Issue import adapter (GitHub Issues label -> agentplan tickets, one-way sync)
- [x] #16 PR automation (branch naming, commit schema, PR create/update)
- [x] #17 State backend v1 (artifact persistence + integrity checks)
- [x] #18 Concurrency controls (workflow concurrency + claim locking + tests)
- [x] #19 Guardrails (max tickets/run, max runtime, budget caps + explicit stop reasons)
- [x] #20 Marketplace listing kit (quickstart, screenshot placeholders, support/security/privacy docs)
- [x] #21 Design Partner pilot script (E2E checklist + metrics capture)
- [x] #22 Self-hosted dashboard secure deployment guide
- [x] #23 Reverse-proxy auth examples (Caddy/Nginx/Cloudflare Access)

## Batch 2 implementation notes (#15-#23)

### Runtime and CLI
- Added `issue import` command:
  - Inputs: project, repo/token, label/state, optional dry-run.
  - Creates/updates tickets from labeled GitHub issues.
  - Persists mapping in `issue_sync_map`.
- Added `pr automate` command:
  - Branch schema: `agentplan/<project>/t<ticket>-<slug>`
  - Commit schema: `agentplan(<project>): ticket #<id> <title>`
  - Creates/updates PRs via `gh` CLI.
- Added `artifact status|verify` commands:
  - Chain state artifact saved to `<project_dir>/.agentplan/artifacts/chain-state.json`.
  - SHA256 tracked in DB (`runtime_artifacts`) and verified on demand.
- Added chain guardrails:
  - default/max `--max-tickets` enforcement + hard cap.
  - `--max-runtime`.
  - `--max-budget-usd` + `--cost-per-ticket-usd`.
  - explicit stop reasons in chain output + persisted state.
- Added claim locking table (`claim_locks`) and lock acquisition/release in `_claim_next_ticket`.

### GitHub usability
- Extended `actions/run-chain/action.yml` with guardrail inputs and extra output `chain-pause-reason`.
- Added workflow template: `.github/workflows/agentplan-marketplace.yml` with workflow-level concurrency.

### Docs and listing assets
- Added/updated:
  - `docs/marketplace/README.md`
  - `docs/marketplace/quickstart.md`
  - `docs/marketplace/support.md`
  - `docs/marketplace/design-partner-pilot-checklist.md`
  - `docs/marketplace/screenshots/*` placeholders
  - `docs/security/security.md`
  - `docs/security/privacy.md`
  - `docs/security/self-hosted-dashboard-secure-deployment.md`
  - `docs/security/reverse-proxy-auth-examples.md`
  - `scripts/design_partner_pilot.sh`

## Tests
- Updated and expanded `test_agentplan.py` coverage for:
  - issue import mapping/idempotency
  - PR automation dry-run/create path
  - artifact tamper detection
  - chain runtime and budget guardrails
  - claim lock acquisition behavior
- Batch validation command run: `pytest test_agentplan.py -q --tb=short`

## Open follow-ups
- Publish hosted versions of support/privacy/security docs and wire stable public URLs in marketplace listing fields.
- Replace screenshot placeholders with real product captures before listing submission.
- Add integration tests for `gh` CLI error-paths in CI environments with mocked auth states.
