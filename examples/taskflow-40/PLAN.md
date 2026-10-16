# TaskFlow: team task tracker (example plan)

> Example of what `bosun:architect` produces in design mode. It pairs with `tasks.json` in this folder (40 tasks). The product and choices are illustrative; items marked `verify:` are exactly that.

## 1. Goal and success criteria
A small-team task tracker: workspaces, projects, a kanban board, comments with mentions, notifications.
Success: a new user can sign up, create a workspace, invite a teammate, create a project and tasks, move tasks across the board and discuss them, with the e2e suite (T35) green and the deploy pipeline (T38) running from main.

## 2. Scope
In: email+password auth, workspaces with roles (owner, admin, member, viewer), projects, tasks, comments, labels, search and filters, activity log, email notifications, OpenAPI docs, container images, CI/CD.
Out (later): SSO, mobile apps, file attachments, real-time collaboration, billing.

## 3. Users and key flows
Team lead creates a workspace and invites members; members create and move tasks; everyone comments and gets notified on mentions and assignment.

## 4. Architecture
pnpm monorepo: `apps/api` (HTTP API + Postgres), `apps/web` (SPA), `packages/shared` (schemas and types used by both).
- API modules live in `apps/api/src/modules/<name>/` and are **discovered automatically** (T04), so feature tasks never edit a central router. This removes the classic merge hotspot.
- Web features live in `apps/web/src/features/<name>/` with **route discovery** (T05) for the same reason.
- All workspace dependencies are installed by T01 so feature tasks don't fight over manifests and the lockfile.

## 5. Tech stack and decisions
- ADR-1 TypeScript end to end, shared schemas in `packages/shared`. Alternative: separate DTOs per app (rejected: drift).
- ADR-2 PostgreSQL with SQL migrations. Alternative: document store (rejected: relational data, constraints).
- ADR-3 Session strategy decided by spike T02 before auth is built. verify: library support for the chosen strategy.
- ADR-4 Passwords: argon2id preferred, bcrypt acceptable. verify: the maintained library for the chosen runtime.

## 6. Data model
users, workspaces, memberships(role), projects, tasks(status, assignee_id), comments, labels, task_labels, activity (append-only), invitations (single-use token, expiry).

## 7. Interfaces and contracts
REST JSON API; one error shape; schemas in `packages/shared` are the contract (T03). OpenAPI served at `/openapi.json` (T22).

## 8. Security and privacy
Assets: accounts, workspace data, invitation tokens. Boundaries: browser to API, API to DB, API to email provider.
Top threats and mitigations: credential stuffing (rate limits T12, uniform login errors T09); cross-tenant access (central policies T11, tests in every module); CSRF if cookie sessions (T12); invitation token theft (single use, expiry, T14); PII in logs (T21 acceptance). Threat-model review: T39.

## 9. Testing strategy
Unit tests next to code; API integration tests against an ephemeral database (harness T06); component tests in web; e2e for the core flow (T35). A task is done when its acceptance criteria are covered by tests that pass in CI.

## 10. Delivery
40 tasks. `taskboard.py waves --parallel 5`: 14 waves, critical path 29 size-units (S=1, M=2, L=3).
Critical chain (computed from the board): T01 → T03 → T07 → T08 → T09 → T10 → T11 → T15 → T28 → T29 → T30 → T35 → T38 → T40, 29 size-units (T04 ties with T03). Auth and authorization must exist before the resource modules, and the board UI waits for the projects UI.
Report tasks: T02 (spike), T34 (accessibility audit), T39 (security review).
Risks: the auth chain is serial (mitigated by front-loading T02, T06 and T07); e2e flakiness (T35 requires 3 consecutive green runs). A revision could shorten the critical path by letting T29 build against the shared Project schema (T03) instead of waiting for T28.
Assumptions: single region; email provider chosen later behind an adapter.
Open questions: session strategy (T02 answers it); do viewers see activity history?

## 11. Operations
Config through environment variables, validated at startup (T04). Migrations run before new versions take traffic (T38). Container images run as non-root (T37). Health endpoint `/health` (T04).
