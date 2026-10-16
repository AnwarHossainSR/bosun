# Spec Delta

## Purpose

Lets people create an account, log in, and prove who they are on every protected request.

## ADDED Requirements

### Requirement: Sign up with email and password
The system SHALL create an account from an email address and a password of at least 12 characters, and SHALL store only a salted hash of the password.

#### Scenario: Valid sign-up
- **WHEN** a visitor signs up with an unused email and a 12-character password
- **THEN** the system returns 201 and the account can log in

#### Scenario: Email already registered
- **WHEN** a visitor signs up with an email that already has an account
- **THEN** the system returns 409 and the existing account is unchanged

#### Scenario: Password too short
- **WHEN** a visitor signs up with an 11-character password
- **THEN** the system returns 422 and creates no account

### Requirement: Log in with email and password
The system SHALL issue a session token when the email and password match an account, and SHALL return the same error for an unknown email and a wrong password.

#### Scenario: Correct credentials
- **WHEN** a user logs in with their email and password
- **THEN** the system returns 200 with a session token

#### Scenario: Wrong password
- **WHEN** a user logs in with a wrong password
- **THEN** the system returns 401 with the same message as for an unknown email

### Requirement: Protected endpoints require a session
The system MUST reject requests to protected endpoints that carry no session token, an unknown token or an expired token.

#### Scenario: Missing token
- **WHEN** a client calls a todo endpoint without a session token
- **THEN** the system returns 401

#### Scenario: Expired token
- **WHEN** a client calls a todo endpoint with a session older than 30 days
- **THEN** the system returns 401
