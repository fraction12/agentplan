# Docs Alignment: Canonical Product Story

This document defines the primary user-facing story for AgentPlan so README, plugin docs, dashboard copy, marketplace material, and support docs all describe the same product.

## Primary positioning

AgentPlan is a shared task board for AI tools.

It is the source of truth for:
- project and ticket state
- dependency order
- ticket claiming
- progress visibility

It is not the primary execution engine.

Execution happens in tools such as Claude Code or Codex, including their loop, cron, or scheduled-task features. AgentPlan tracks the work those tools plan and perform.

## Primary user workflow

The default workflow we should document is:

1. A user opens Claude Code, Codex, or another supported AI tool.
2. The AI plans the work and creates an AgentPlan project linked to the repo.
3. The AI breaks the work into small tickets with dependencies.
4. The AI or user checks `agentplan next` / `agentplan claim` to pick unblocked work.
5. The AI executes the ticket in its own environment or loop.
6. AgentPlan records completion, logs, and remaining backlog state.
7. The user watches progress in the dashboard.

Short version:

Plan in the AI tool. Track in AgentPlan. Execute through the AI tool's own loop or scheduled workflow.

## What should be primary in user-facing docs

These concepts should be front-and-center:
- shared backlog for AI agents
- local-first task tracking
- dependency-aware ticket queue
- atomic claim to avoid duplicate work
- dashboard visibility
- works across Claude Code, Codex, and other tools

## What should be de-emphasized

These concepts should not lead the story in user-facing docs:
- built-in chain orchestration
- internal routing/control-plane mechanics
- low-level agent registry internals
- deprecated or power-user orchestration flows

They can still exist in advanced docs, but they should not define the product for new users.

## Messaging rules

Use these phrases consistently:
- "shared task board for AI tools"
- "source of truth for task state"
- "plan in Claude/Codex, track in AgentPlan"
- "claim the next unblocked ticket"
- "use the dashboard for visibility"

Avoid making these the headline:
- "run-chain"
- "chain controller"
- "agent orchestration engine"
- "autonomous controller"

If loops are mentioned, describe them as features of the host AI tool or operator workflow, not as AgentPlan's core identity.

## Product boundary

AgentPlan should read as:
- coordination layer
- task ledger
- execution state tracker

AgentPlan should not read as:
- full IDE agent runtime
- scheduler platform
- CI orchestrator first

Those can be integrations or advanced workflows.

## Current docs drift to fix

The main drift today is inconsistency between the repo's current product direction and older orchestration-heavy docs.

### Primary drift themes

- README mostly tells the right story, but still carries loop wording that can imply AgentPlan itself runs the execution workflow.
- Claude plugin docs mix "AgentPlan as source of truth" with older cron/orchestration framing.
- Marketplace docs still feature chain-heavy examples and screenshots.
- Security/privacy/support docs still mention chain state more prominently than the primary workflow warrants.
- Some always-loaded plugin guidance still exposes large internal command surfaces that are not part of the desired public mental model.

### Files that should be updated next

- `README.md`
- `agentplan/plugins/claude-code/README.md`
- `agentplan/plugins/claude-code/CLAUDE.md`
- `agentplan/plugins/claude-code/commands/loop.md`
- `agentplan/plugins/codex/SKILL.md`
- `docs/marketplace/README.md`
- `docs/marketplace/quickstart.md`
- `docs/marketplace/support.md`
- `docs/security/privacy.md`
- dashboard copy and other user-facing templates where old orchestration language still appears

## Documentation policy going forward

When a doc is for new users, leads, or evaluators:
- lead with the shared-task-board story
- show the Claude/Codex planning workflow
- show claim/dependency/dashboard behavior
- keep orchestration internals out of the opening explanation

When a doc is for advanced operators:
- clearly label orchestration, routing, CI, or headless flows as advanced/internal
- explain how they extend the core workflow rather than replace it

## Exit criteria for the docs refresh

The docs refresh is complete when:
- a new reader can understand AgentPlan in under a minute
- the README, plugin docs, and dashboard copy all describe the same workflow
- advanced orchestration features no longer confuse the main story
- demo and marketplace materials reflect the actual intended user journey
