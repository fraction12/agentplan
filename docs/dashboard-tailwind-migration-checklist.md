# Dashboard Tailwind/Alpine Migration Parity Checklist

This checklist defines the current dashboard behaviors that must survive the Alpine.js + Tailwind migration in `dashboard-polish-alpinejs-tailwind-migration`.

## Global Shell

- Preserve the base shell from [`agentplan/dashboard/templates/base.html`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/templates/base.html):
  - top navigation with `Home` and `Activity`
  - live clock
  - SSE connection indicator
  - favicon link
- Preserve `/favicon.ico` redirect behavior from [`agentplan/dashboard/routes.py`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/routes.py).
- Preserve shared client helpers currently provided by [`agentplan/dashboard/static/dashboard.js`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/static/dashboard.js):
  - `showToast(...)`
  - `setClock(...)`
  - `setConnection(...)`
  - `subscribeSSE(...)`
  - `confirmAction(...)`
- The Alpine migration may replace the implementation, but it must preserve equivalent capabilities and page-level wiring.

## Security And API Invariants

- Preserve origin protection from [`_require_local_origin`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/routes.py) and `_origin_matches_request_host(...)`:
  - same scheme, host, and effective port required for non-loopback requests
  - loopback origins remain allowed
- Do not reintroduce reflected input in JSON responses.
- Do not rebuild SQL dynamically from request-controlled fields in transition paths.
- Preserve the `303` redirect behavior for `POST /api/project/create`.
- Preserve existing ticket transition validation and canonical error messages.
- Preserve dependency cycle rejection in ticket dependency APIs.

## Home Page

- Preserve homepage sections from [`agentplan/dashboard/templates/home.html`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/templates/home.html):
  - `Active Projects`
  - `Completed Projects`
  - `Closed Projects`
  - `Archived Projects`
- Sections must remain collapsible.
- Section expanded/collapsed state must persist across reloads and SSE refreshes.
- Preserve the create-project dialog flow:
  - title required
  - optional description
  - optional directory
  - success redirects to the new project page
- Preserve project card behavior:
  - card links into the project page
  - kebab menu is outside the card link
  - `Close`, `Archive`, `Delete` actions remain status-aware
  - status badge remains visible
  - progress ring and done count remain visible
  - last activity timestamp remains visible
  - missing-directory warning remains visible
- Preserve homepage summary metrics:
  - active projects counts only truly active projects
  - tickets in flight
  - completed today
- Preserve live homepage updates from `project_stats` SSE payloads.
- Preserve empty states for no projects and empty status sections.

## Project Page

- Preserve project header actions from [`agentplan/dashboard/templates/project.html`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/templates/project.html):
  - project kebab menu
  - `Close`, `Archive`, `Delete`
- Preserve editable linked-directory behavior:
  - display current directory or empty state
  - edit/save/cancel controls
  - missing-directory warning
- Preserve project context behavior:
  - render existing context content
  - empty-state message when context file does not exist
  - generate/regenerate context action
  - poll/refresh context status
- Preserve add-ticket dialog:
  - title required
  - optional description
  - constrained priority choices
- Preserve filters:
  - status
  - priority
  - tag
  - apply/reset
- Preserve kanban board semantics:
  - columns for `pending`, `in-progress`, `blocked`, `needs-review`, `failed`, `done`
  - cards in terminal states are not draggable
  - drag/drop transitions must still validate through the server
  - blocked tickets remain grouped correctly
  - subtask progress remains visible on cards
  - assignee and tags remain visible when present
- Preserve ticket side panel behavior now implemented in [`agentplan/dashboard/static/project.js`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/static/project.js):
  - open ticket detail panel from the board
  - title edit from panel header
  - delete ticket from overflow menu
  - field editor modal for title, description, priority
  - subtask add and mark-done flows
  - dependency chip UI for `Blocked by` and `Blocking`
  - dependency add/remove flows
  - dismissal behavior for menus, picker, and panel via click-outside and Escape
  - toast feedback on failures
- Preserve live board updates from `project_board` SSE payloads.
- Preserve hidden chain UI state:
  - the chain controls stay hidden in the UI
  - chain APIs and chain fields in the payload remain intact unless explicitly removed in a later scoped project

## Ticket Detail Page

- Preserve standalone ticket detail route and page from [`agentplan/dashboard/templates/ticket.html`](/Users/dushyant_jarvis/Documents/Projects/agentplan/agentplan/dashboard/templates/ticket.html).
- Preserve visible data:
  - title
  - status
  - priority
  - tags
  - description
  - close notes when present
  - dependencies
  - subtasks
  - history/audit log
- Preserve back navigation to the parent project.
- This page currently uses a separate Bootstrap-based shell. If migrated into the shared Alpine/Tailwind shell, content parity must still hold.

## Activity Page

- Preserve activity feed route and live SSE updates.
- Preserve filter behavior:
  - agent filter pills
  - action filter pills
- Preserve created-event collapsing logic:
  - bursts of ticket creation collapse into a grouped row
- Preserve relative-time and day grouping behavior.
- Preserve active-agent presence line.
- Preserve ticket/project links in rendered feed rows.

## Agents Page

- Preserve agents listing and detected tools view.
- Preserve CRUD flows:
  - add agent
  - edit agent inline
  - delete agent
- Preserve role assignment checkboxes.
- Preserve the current edit-row open/close interaction model unless intentionally redesigned.
- Preserve SSE connection indicator behavior on this page.

## SSE Contract

- Preserve `/events` and `/stream`.
- Preserve current event names:
  - `project_stats`
  - `activity_feed`
  - `project_board` when a project slug is supplied
- Preserve current page-level behavior when SSE is unsupported, connected, reconnecting, or parse-failing.

## Regression Coverage Targets

- The migration must keep or replace the current dashboard coverage represented by the dashboard test block in [`test_agentplan.py`](/Users/dushyant_jarvis/Documents/Projects/agentplan/test_agentplan.py).
- At minimum, preserve automated checks for:
  - homepage project sections, menus, badges, collapsible behavior, archived section, favicon
  - project page menus, directory editing, context content, kanban drag/drop logic, panel controls
  - ticket edit, delete, transition, subtask, dependency, and log endpoints
  - origin-guard enforcement
  - chain start/stop behavior
  - activity and agents routes
  - SSE and stats endpoints

## Cleanup Gate

- Do not delete `style.css`, `dashboard.js`, `project.js`, or `agents.js` until:
  - every migrated page meets this checklist
  - regression coverage is updated
  - manual QA passes across home, project, ticket, activity, and agents
