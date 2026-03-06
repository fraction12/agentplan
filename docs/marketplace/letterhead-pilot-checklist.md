# Letterhead Pilot Checklist

## E2E validation
- [ ] Setup action installs expected version (`actions/setup`).
- [ ] Issue import maps `label=agentplan` issues into project tickets.
- [ ] Run-chain action executes in CI mode and emits outputs.
- [ ] Guardrails stop with explicit reasons when limits are hit.
- [ ] PR automation dry run prints branch/commit/PR schema.
- [ ] Runtime artifact integrity verifies (`agentplan artifact verify <project>`).

## Success metrics to capture
- workflow run duration (seconds)
- tickets imported count
- tickets processed count
- final chain status
- stop/pause reason (if any)
- count of failed workflows

Use `scripts/letterhead_pilot.sh` to capture this into a timestamped report.
