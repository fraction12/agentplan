# Privacy

> **Note:** AgentPlan primarily stores shared project and ticket state for AI work. Advanced orchestration and CI references below apply only when operators enable those workflows.

`agentplan` stores project and ticket metadata in SQLite. In CI workflows, logs may include project slugs, ticket titles, and execution status.

## Data stored locally
- project metadata (slug, title, optional directory path)
- ticket metadata (title, description, tags, status)
- runtime logs and advanced automation state
- imported GitHub issue references (repo, issue number, URL)

## Data sent externally
- only to services explicitly configured by the operator (for example GitHub API, agent command templates, webhook targets)

## Retention
- controlled by operator-managed DB and workflow log retention settings
