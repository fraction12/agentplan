---
allowed-tools: Bash(agentplan:*), AskUserQuestion, CronCreate, CronList, CronDelete
description: Set up a cron loop to autonomously work through tickets
---

# /agentplan:loop

Interactively configure a cron job that autonomously picks up agentplan tickets, does the work, and marks them done.

## Steps

1. **Identify the project.** Check for projects linked to the current directory:
   ```bash
   agentplan list
   ```
   If ambiguous, ask the user which project.

2. **Show current state** so the user knows what's queued:
   ```bash
   agentplan status <project>
   ```

3. **Ask the user to configure the loop:**
   - **Interval**: How often should it run? (e.g., every 10 minutes, every hour)
   - **Scope**: Work through all unblocked tickets, or stop after N tickets?
   - **On failure**: Should it stop the loop, skip the ticket, or mark it failed and continue?
   - **Validation**: Should it run tests/build after each ticket?

4. **Create the cron job** using CronCreate with this prompt template (fill in the project and settings from the user's answers):

   ```
   You are running an autonomous agentplan work loop.

   Project: <project>

   Algorithm:
   1. Run: agentplan next <project>
   2. If no unblocked ticket is returned, report "No unblocked tickets for <project>" and stop.
   3. Claim the ticket: agentplan claim <project>
      - If claim fails (race condition), go back to step 1.
   4. Read the claimed ticket details (title, description, dependencies, notes).
   5. Implement exactly what the ticket asks. Keep changes scoped to this ticket only.
   6. <validation_step>
   7. Commit your changes with a clear message referencing the ticket.
   8. Mark done: agentplan ticket done <project> <ticket_num>
   9. Log: agentplan log <project> --ticket <ticket_num> "Completed: <summary>. Validation: <result>."
   10. <continuation_rule>

   On failure:
   - <failure_behavior>

   Rules:
   - Do not start work without claiming first.
   - Only work tickets surfaced by next/claim (respect dependencies).
   - Keep changes scoped to the claimed ticket.
   ```

   Replace placeholders based on user's answers:
   - `<validation_step>`: "Run tests/build for the changed scope." or "Skip validation." based on user preference.
   - `<continuation_rule>`: "Stop after this ticket." or "Continue to the next ticket immediately." based on scope preference. If the user said stop after N, track count.
   - `<failure_behavior>`: "Stop the loop and report the blocker." or "Mark failed: `agentplan ticket fail <project> <ticket_num> --reason '<error>'` and continue to next ticket." based on user preference.

5. **Confirm the cron job was created.** Show the user:
   - The interval and schedule
   - What project it's working on
   - How to check progress: `agentplan status <project>` or `/agentplan:status`
   - How to cancel: they can ask you to cancel the loop or use CronDelete
   - Remind them: cron jobs only run in this session and auto-expire after 3 days

## Defaults (if user says "just do it")

- Interval: every 10 minutes
- Scope: work through all unblocked tickets
- On failure: mark failed and continue to next ticket
- Validation: run tests if a test suite is detected
