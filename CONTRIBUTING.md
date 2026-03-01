# Contributing to agentplan

## Development Setup

1. Clone the repository and enter it:
   ```bash
   git clone https://github.com/fraction12/agentplan.git
   cd agentplan
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install the project in editable mode with development dependencies:
   ```bash
   pip install -e .[dev]
   ```

## Running Tests

The test suite should run against a temporary SQLite database.

- Primary command:
  ```bash
  AGENTPLAN_DB=/tmp/test_agentplan.db pytest test_agentplan.py -v
  ```
- Full verbose run:
  ```bash
  pytest -v
  ```

Notes:
- `test_agentplan.py` uses a pytest fixture that sets `AGENTPLAN_DB` to `/tmp/test_agentplan.db` and initializes a clean schema per test.
- Avoid running tests against your real local database.

## Pull Request Guidelines

### Branch naming

Use descriptive branch names with a short prefix:

- `feat/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`
- `test/<short-description>`
- `chore/<short-description>`

Examples: `feat/claim-command`, `fix/dependency-validation`, `docs/contributing-guide`.

### Commit style

Keep commits small and focused. Use an imperative subject line:

- `feat: add ticket claim command`
- `fix: handle missing project slug`
- `docs: add contribution workflow`
- `test: add coverage for claim concurrency`

### What to include in a PR

Each PR should include:

1. A clear summary of what changed and why.
2. Any relevant context or design decisions.
3. Test evidence (commands run and results), at minimum:
   - `AGENTPLAN_DB=/tmp/test_agentplan.db pytest test_agentplan.py -v`
   - `pytest -v`
4. Notes about backward compatibility, migrations, or CLI behavior changes (if applicable).
5. Linked issue(s) when available.

Keep PRs scoped; prefer multiple small PRs over one large mixed change.
