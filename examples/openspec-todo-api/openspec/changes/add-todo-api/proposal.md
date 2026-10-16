# Proposal

## Why

People want a simple API to keep a private todo list that they can reach from any client. There is no service yet, so this change creates it with accounts and per-user privacy from day one.

## What Changes

- New HTTP API with sign-up, login and session-protected endpoints.
- New todo endpoints to create, list, update, complete and delete items.
- Every todo item belongs to one user and is invisible to everyone else.

## Capabilities

### New Capabilities
- `user-accounts`: sign-up, login and session checks for protected endpoints.
- `todo-items`: creating, reading, updating and deleting a user's own todo items.

### Modified Capabilities

## Impact

- New service: HTTP API, database schema and migrations, CI workflow.
- Stores email addresses and password hashes, so it handles personal data.
