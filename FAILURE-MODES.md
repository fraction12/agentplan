# FAILURE-MODES.md — agentplan Failure Modes & Recovery

This document covers known failure scenarios, their causes, and recovery steps for `agentplan`.

---

## 1. Process Crashes Mid-Ticket

**Scenario:** The agent process is killed (SIGTERM, OOM, power loss) while a ticket is `in-progress`.

**Effect:** The ticket remains `in-progress` indefinitely. No completion is recorded. The project is effectively stalled until manually recovered.

**Detection:** `agentplan next <project>` will surface the orphaned in-progress ticket at the top of the list. It will show `▶` status.

**Recovery:**
- If the work was completed before the crash:  
  `agentplan ticket done <project> <id>`
- If the work needs to be retried:  
  `agentplan ticket start <project> <id> --agent <agent>` (re-claims it)  
  or use `agentplan reap <project>` if a `--timeout` was set
- If the ticket used `--timeout`: the next `agentplan next` or `agentplan claim` call will auto-reap it back to `pending`.

**Prevention:** Always set `--timeout` when claiming tickets via automated agents:  
`agentplan claim <project> --agent mybot --timeout 300`

---

## 2. Stale Claims (Agent Hung / Disconnected)

**Scenario:** An agent claimed a ticket but stopped responding — hung process, network drop, timeout, or crash.

**Effect:** Ticket stays `in-progress`. No other agent can claim it. Chain controller stalls.

**How `claim_timeout` works:**
- Set via `agentplan claim <project> --timeout <seconds>`
- Stored as `claim_timeout` on the ticket row
- Evaluated lazily: the next `next`, `claim`, or `reap` call reclaims expired tickets automatically

**Auto-reap:** `agentplan next` and `agentplan claim` call `_reap_expired_claims` before returning results. Any ticket whose `claimed_at + claim_timeout < now` is reset to `pending`.

**Manual reap:**  
`agentplan reap <project>` — immediately reclaims all expired tickets and prints the count.

**Edge case — pre-existing negative timeout rows:** Rows inserted before timeout validation was added may have `claim_timeout <= 0`. These are treated as already-expired and reclaimed immediately on the next reap pass.

---

## 3. Dependency Deadlocks

**Scenario:** Ticket A depends on B, and B depends on A (circular dependency).

**Effect:** Both tickets show as `blocked`. Neither can ever become unblocked. `agentplan next` returns no results for the project.

**Detection:** `agentplan status <project>` — all remaining tickets show `⏳ (blocked)`.

**Recovery:**
```
agentplan undepend <project> <ticket_a> <ticket_b>
```
Remove one dependency to break the cycle, then re-plan the work order.

**Prevention:** The dependency system does not currently enforce acyclicity at creation time. Manually verify dependency order when chaining tickets.

---

## 4. Concurrent Agent Writes (Race Conditions)

**Scenario:** Two agents simultaneously claim the same ticket or update the same row.

**Effect (without protection):** Both agents think they own the ticket. Duplicate work, inconsistent state.

**How agentplan mitigates this:**
- SQLite WAL mode (`PRAGMA journal_mode=WAL`) is enabled — allows concurrent readers, serializes writers.
- Claim uses an atomic `UPDATE ... WHERE status='pending'` with `rowcount` check. If `rowcount == 0`, the claim failed (another agent got there first). The caller gets no ticket.
- This is a compare-and-swap pattern: only one agent wins the race.

**Residual risk:** SQLite WAL is not distributed. If two processes share the same `.db` file over NFS or a network share, locking semantics are unreliable. Use agentplan on local filesystems only.

---

## 5. Ticket State Machine Violations

**Valid transitions:**

```
pending → in-progress → done
                      → blocked
                      → failed
                      → needs-review
                      → skipped
blocked → pending (manual unblock)
failed  → pending (manual retry via ticket start)
needs-review → done | pending
```

**Invalid transitions** (e.g., `done → in-progress`) are rejected with an error:  
`Ticket #X transition blocked: cannot move from done to in-progress`

**Recovery:** If a ticket is stuck in a terminal state incorrectly, use:  
`agentplan ticket update <project> <id> --status pending`  
(direct status override for recovery purposes).

---

## 6. Auto-Complete Fires Prematurely

**Scenario:** All tickets appear done but some were skipped rather than completed. The project auto-completes.

**Effect:** Project status flips to `closed`. In-flight work may be cut off.

**How it works:** `check_auto_complete` considers a project complete when all tickets are in `{done, skipped, failed}`. Skipped tickets count as "resolved."

**Recovery:**  
`agentplan ticket update <project> <id> --status pending` to reopen a skipped ticket.  
The project will not auto-close again until all tickets are terminal.

---

## 7. DB Corruption / Missing Schema Columns

**Scenario:** agentplan is upgraded but the local `.db` file predates new columns (e.g., `claimed_at`, `claim_timeout`).

**Effect:** SQL errors on column access, or missing features silently fail.

**How agentplan handles this:** `ensure_schema` runs `ALTER TABLE IF NOT EXISTS` migration statements for new columns on every `get_connection()`. Safe to re-run; SQLite ignores `IF NOT EXISTS` on existing columns.

**Manual check:**  
```bash
sqlite3 ~/.agentplan/agentplan.db ".schema tickets"
```

---

## 8. Log/History Overflow

**Scenario:** High-frequency agents logging every turn — the `log` and `ticket_history` tables grow unbounded.

**Effect:** Slower queries, larger DB file.

**Current behavior:** No automatic pruning. Logs and history are append-only.

**Mitigation:** Periodically vacuum the DB:  
```bash
sqlite3 ~/.agentplan/agentplan.db "VACUUM;"
```

---

## Quick Reference

| Problem | Command |
|---|---|
| Stale in-progress ticket | `agentplan reap <project>` |
| Circular dependency | `agentplan undepend <project> <a> <b>` |
| Wrong terminal state | `agentplan ticket update <project> <id> --status pending` |
| Force-complete ticket | `agentplan ticket done <project> <id>` |
| Schema check | `sqlite3 ~/.agentplan/agentplan.db ".schema"` |
| DB vacuum | `sqlite3 ~/.agentplan/agentplan.db "VACUUM;"` |
