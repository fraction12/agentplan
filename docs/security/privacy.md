# Privacy

> **Note:** References to chaining/routing/orchestration below are advanced/internal workflows for power users and are de-emphasized in the main AgentPlan UX.

`agentplan` stores project and ticket metadata in SQLite. In CI workflows, logs may include project slugs, ticket titles, and execution status.

## Data stored locally
- project metadata (slug, title, optional directory path)
- ticket metadata (title, description, tags, status)
- runtime logs and chain state
- imported GitHub issue references (repo, issue number, URL)

## Data sent externally
- only to services explicitly configured by the operator (for example GitHub API, agent command templates, webhook targets)

## Retention
- controlled by operator-managed DB and workflow log retention settings
