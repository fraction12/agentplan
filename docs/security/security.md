# Security

## Reporting a vulnerability
Please report vulnerabilities privately through repository security advisories or private maintainer contact. Do not open public issues for undisclosed vulnerabilities.

## Scope
- CLI runtime behavior
- database/state persistence
- dashboard exposure and auth boundaries
- GitHub workflow integrations

## Hardening defaults
- Run dashboard behind authenticated reverse proxy.
- Keep `AGENTPLAN_DB` file permissions strict (`0600`).
- Restrict GitHub token permissions to minimum required scopes.
- Use short-lived credentials in CI.
