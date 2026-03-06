# agentplan-setup (Composite Action)

Install `agentplan` from PyPI and expose the resolved version for later workflow steps.

## Usage

```yaml
- name: Setup agentplan
  id: setup-agentplan
  uses: ./actions/setup
  with:
    version: "0.6.4"

- name: Print resolved version
  run: echo "agentplan=${{ steps.setup-agentplan.outputs.agentplan-version }}"
```

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `version` | No | `""` | Optional `agentplan` version (for example `0.6.4`). Empty installs latest. |

## Outputs

| Name | Description |
|---|---|
| `agentplan-version` | Installed `agentplan` version after validation. |

## Behavior

- Upgrades `pip`.
- Installs `agentplan` (latest or exact version).
- Validates installed version when `version` is provided.
