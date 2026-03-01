# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Placeholder for upcoming changes.

## [0.2.0] - 2026-03-01

### Added
- Ticket priority support with `--priority` and priority-aware ordering in `next`.
- Close notes on `ticket done` via `--note`.
- Ticket labels/tags via `--tag`, plus filtering in `next`, `status`, and `claim`.
- Subtasks/checklists with `subtask add|done|list` and progress indicators.
- Agent identity tracking with `--agent` on `ticket start`, `ticket done`, and `claim`.
- Atomic `claim` command for concurrency-safe ticket claiming.
- Ticket descriptions on create with `ticket add --desc`.
- `ticket edit` command with `--title`, `--desc`, `--priority`, `--tag`, and `--due`.
- Due dates (`--due`) with overdue-aware prioritization in `next`.
- Cross-project full-text ticket search with `search`.
- `archive` command for completed/abandoned projects.
- Bulk completion support in `ticket done` (space-separated and comma-separated IDs).
- JSON output for `next --format json` and `status --format json`.
- Ticket state audit log with `history` (state transitions + timestamps).
- Shell completion generation for `bash`, `zsh`, and `fish` via `completion`.
- Human-friendly CLI errors with actionable suggestions.
- `llms.txt` and `llms-full.txt` for agent discoverability.
- `CONTRIBUTING.md` with setup, testing, and PR guidance.

### Changed
- `list` now hides archived projects by default and supports `--all` to include them.
- Status output includes a concise summary line and richer ticket metadata display.
- Adding a new ticket can reopen projects in `completed`, `abandoned`, or `archived`.
- Parser/packaging updates, including CLI entry point and expanded pytest coverage.

