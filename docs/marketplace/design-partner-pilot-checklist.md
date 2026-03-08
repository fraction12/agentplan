# Design Partner Pilot Checklist

> **Note:** This checklist is for Marketplace/CI design partners. It covers advanced automation paths in addition to the core AgentPlan workflow.

## E2E validation
- [ ] Setup action installs expected version (`actions/setup`).
- [ ] Issue import maps `label=agentplan` issues into project tickets.
- [ ] Advanced run-chain action executes in CI mode and emits outputs.
- [ ] Guardrails stop with explicit reasons when limits are hit.
- [ ] PR automation dry run prints branch/commit/PR schema.
- [ ] Runtime artifact integrity verifies (`agentplan artifact verify <project>`).

## Success metrics to capture
- workflow run duration (seconds)
- tickets imported count
- tickets processed count
- final automation status
- stop/pause reason (if any)
- count of failed workflows

Use `scripts/design_partner_pilot.sh` to capture this into a timestamped report.
