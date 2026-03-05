# GitHub Marketplace Quickstart (Phase 1)

This quickstart shows how to use the Phase 1 actions added in this repository.

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

## 2) Run chain headlessly in CI

```yaml
- name: Run agentplan chain
  id: run-chain
  uses: ./actions/run-chain
  with:
    project-slug: my-project
    max-tickets: "2"
    timeout: "1800"

- name: Echo final status
  run: echo "status=${{ steps.run-chain.outputs.chain-status }}"
```

Notes:
- `actions/run-chain` forces `AGENTPLAN_CI=1`, so no terminal spawning is used.
- The action writes a Markdown summary to `$GITHUB_STEP_SUMMARY`.
- `max-tickets` and `timeout` are optional.
