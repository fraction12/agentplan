# GitHub Marketplace Quickstart (Phase 1)

> **Note:** This quickstart covers Marketplace and CI/operator workflows. The primary product workflow is still: plan in Claude/Codex, track in AgentPlan, and use the dashboard for visibility.

This quickstart shows how to use the Phase 1 actions added in this repository for CI and GitHub Marketplace scenarios.

## 1) Install agentplan in a workflow

```yaml
- name: Setup agentplan
  id: setup-agentplan
  uses: ./actions/setup
  with:
    version: "0.6.4"

- name: Echo installed version
  run: echo "agentplan=${{ steps.setup-agentplan.outputs.agentplan-version }}"
```

## 2) Run advanced automation headlessly in CI

```yaml
- name: Run agentplan chain
  id: run-chain
  uses: ./actions/run-chain
  with:
    project-slug: my-project
    max-tickets: "2"
    timeout: "1800"
    max-runtime: "3600"
    max-budget-usd: "10"
    cost-per-ticket-usd: "0.25"

- name: Echo final status
  run: |
    echo "status=${{ steps.run-chain.outputs.chain-status }}"
    echo "reason=${{ steps.run-chain.outputs.chain-pause-reason }}"
```

Notes:
- This is an advanced CI/operator path, not the default user flow.
- `actions/run-chain` forces `AGENTPLAN_CI=1`, so no terminal spawning is used.
- The action writes a Markdown summary to `$GITHUB_STEP_SUMMARY`.
- `max-tickets` and `timeout` are optional.
- `max-runtime`, `max-budget-usd`, and `cost-per-ticket-usd` are optional guardrails.

## 3) Import labeled GitHub issues into tickets

```yaml
- name: Import issue backlog
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITHUB_REPOSITORY: ${{ github.repository }}
  run: agentplan issue import my-project --label agentplan --state open
```

## 4) PR automation for a ticket

```bash
agentplan pr automate my-project --ticket-id 12 --base main --dry-run
```
