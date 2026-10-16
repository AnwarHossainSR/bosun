# Tasks

## 1. Foundation

- [ ] 1.1 Scaffold the API project, tooling, CI and a README with setup steps; verify `npm test` and `npm run lint` pass and GET /health returns 200
- [ ] 1.2 Define shared types, the session interface and the database schema with its first migration; verify the migration applies to an empty database

## 2. User accounts

- [ ] 2.1 Implement sign-up with salted password hashes; verify the valid, duplicate-email and short-password scenario tests pass
- [ ] 2.2 Implement login and session tokens; verify the correct-credentials and wrong-password scenario tests pass
- [ ] 2.3 Add the session middleware for protected endpoints and document authentication in docs/auth.md; verify the missing-token and expired-token scenario tests pass

## 3. Todo items

- [ ] 3.1 Implement creating and listing todo items with owner checks; verify the create, list and privacy scenario tests pass
- [ ] 3.2 Implement updating, completing and deleting todo items with owner checks and document the todo endpoints in docs/todos.md; verify the update, delete and privacy scenario tests pass

## 4. Integration

- [ ] 4.1 Run an end-to-end test of sign-up, login and the todo lifecycle against a local server; verify it passes in CI

## Workflow follow-up

- Archive the change after review with `/bosun:archive add-todo-api`.
