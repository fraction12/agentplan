# agentplan-run-chain (Composite Action)

Run an `agentplan chain` headlessly in CI and publish a detailed run summary to GitHub step summary.

## Usage

```yaml
- name: Run chain
  id: run-chain
  uses: ./actions/run-chain
  with:
    project-slug: my-project
    max-tickets: "5"
    timeout: "1800"
    max-runtime: "3600"
    max-budget-usd: "10"
    cost-per-ticket-usd: "0.25"

- name: Show outputs
  run: |
    echo "status=${{ steps.run-chain.outputs.chain-status }}"
    echo "reason=${{ steps.run-chain.outputs.chain-pause-reason }}"
```

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `project-slug` | Yes | n/a | Project slug to execute. |
| `max-tickets` | No | `""` | Optional max number of tickets to process. |
| `timeout` | No | `""` | Optional per-ticket timeout in seconds. |
| `max-runtime` | No | `""` | Optional max runtime in seconds. |
| `max-budget-usd` | No | `""` | Optional budget cap in USD. |
| `cost-per-ticket-usd` | No | `"0"` | Estimated ticket cost used with budget cap. |

## Outputs

| Name | Description |
|---|---|
| `chain-status` | Final chain status from `agentplan chain --status`. |
| `chain-pause-reason` | Pause/stop reason (if available). |

## Behavior

- Forces CI-safe mode with `AGENTPLAN_CI=1`.
- Captures chain output and chain status.
- Writes a markdown summary to `$GITHUB_STEP_SUMMARY`.
- Fails the step when the chain command exits non-zero.
