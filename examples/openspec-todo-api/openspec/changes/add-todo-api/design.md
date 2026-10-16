# Design

## Context

New service, no existing code. See proposal.md for the motivation. The service handles personal data (email addresses) and credentials, so security decisions are made up front.

## Goals / Non-Goals

**Goals:**
- One small HTTP service with a relational database.
- Contracts first: shared types and the session interface exist before features, so the account and todo work can proceed in parallel.

**Non-Goals:**
- Password reset, email verification, sharing lists between users.

## Decisions

- **Opaque session tokens stored server-side** instead of self-contained signed tokens: logout and revocation stay simple. Alternative considered: signed tokens, rejected because revocation needs extra state anyway.
- **Password hashing with a memory-hard algorithm (argon2id, or bcrypt if unavailable).** verify: the chosen library's current recommended parameters before implementing.
- **Ownership checks in the data-access layer**: every todo query filters by the owner, so a route cannot forget the check.
- **Not-found instead of forbidden** for other users' items, so item ids leak nothing.

## Risks / Trade-offs

- [Session table grows without bound] → expire sessions after 30 days and delete expired rows on login.
- [Timing differences reveal which emails exist] → hash a dummy password when the email is unknown.

## Migration Plan

New database; the first migration creates the users, sessions and todo tables. Rollback: drop the database.

## Open Questions

- Session lifetime may be tuned after launch; 30 days for now.
