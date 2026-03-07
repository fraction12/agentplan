# Self-Hosted Dashboard Secure Deployment Guide

> **Note:** References to chaining/routing/orchestration below are advanced/internal workflows for power users and are de-emphasized in the main AgentPlan UX.

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
- Verify `agentplan chain <project> --status` from host shell.
- Verify reverse proxy auth before exposing dashboard URL.
- Back up SQLite DB on a schedule.
