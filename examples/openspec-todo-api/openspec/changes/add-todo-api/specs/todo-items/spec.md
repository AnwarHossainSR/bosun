# Spec Delta

## Purpose

Lets each signed-in user keep a private list of todo items and work through it.

## ADDED Requirements

### Requirement: Create todo item
The system SHALL create a todo item for the signed-in user when given a title of 1 to 200 characters.

#### Scenario: Valid title
- **WHEN** a signed-in user creates a todo with the title "Buy milk"
- **THEN** the system returns 201 with the new item, marked not done

#### Scenario: Empty title
- **WHEN** a signed-in user creates a todo with an empty title
- **THEN** the system returns 422 and creates nothing

### Requirement: List own todo items
The system SHALL list the signed-in user's todo items, newest first.

#### Scenario: Items listed newest first
- **WHEN** a user who created "A" and then "B" lists their items
- **THEN** the system returns "B" before "A"

### Requirement: Update and complete todo item
The system SHALL let the owner change an item's title and mark it done or not done.

#### Scenario: Mark done
- **WHEN** the owner marks an item done
- **THEN** later reads show the item as done

### Requirement: Delete todo item
The system SHALL let the owner delete an item permanently.

#### Scenario: Delete
- **WHEN** the owner deletes an item
- **THEN** the system returns 204 and the item no longer appears in the list

### Requirement: Todo items are private
The system SHALL NOT reveal, change or delete a todo item for anyone but its owner, and SHALL answer such requests as if the item did not exist.

#### Scenario: Another user's item
- **WHEN** user A reads, updates or deletes an item owned by user B
- **THEN** the system returns 404 and the item is unchanged
