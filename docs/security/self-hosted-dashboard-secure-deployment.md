# Self-Hosted Dashboard Secure Deployment Guide

> **Note:** AgentPlan's primary workflow is shared project and ticket management for AI tools. Advanced automation and orchestration checks below apply only if you enable those operator workflows.

## Baseline
1. Bind dashboard to localhost only:
   - `agentplan dashboard --host 127.0.0.1 --port 5001`
2. Put a reverse proxy in front with SSO or mTLS.
3. Deny direct public access to dashboard port.

## Runtime hardening
- Run under a dedicated OS user.
- Store `AGENTPLAN_DB` in a restricted directory.
- Set file permissions to owner read/write only.
- Rotate logs and avoid writing secrets to ticket descriptions/notes.

## Network controls
- Allow inbound only from reverse proxy.
- Enforce HTTPS at the edge.
- Add request size/rate limits on proxy paths.

## Operational checks
- Verify `agentplan status <project>` from host shell.
- If advanced automation is enabled, also verify `agentplan chain <project> --status`.
- Verify reverse proxy auth before exposing dashboard URL.
- Back up SQLite DB on a schedule.
