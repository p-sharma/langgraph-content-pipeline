# post-archive-api Specification

## Purpose

Lets clients, starting with the archive page, list and read published posts over HTTP. These endpoints are read-only and do not depend on the run that produced the post still being reachable.

## Requirements

### Requirement: List published posts
The API SHALL provide `GET /posts`, which returns published posts newest first. Each item SHALL include the run ID, topic, draft text, references, publication time, critic verdict and edited flag.

#### Scenario: Posts in newest-first order
- **WHEN** a client requests `GET /posts` and two posts exist
- **THEN** the response is 200 with both posts
- **AND** the most recently published post comes first

#### Scenario: No posts yet
- **WHEN** a client requests `GET /posts` and no posts exist
- **THEN** the response is 200 with an empty list

### Requirement: Paginate the post list
`GET /posts` SHALL accept `limit` (default 20, from 1 to 100) and `offset` (default 0, at least 0) query parameters, and SHALL reject values outside these ranges.

#### Scenario: Limit applied
- **WHEN** a client requests `GET /posts?limit=1` and two posts exist
- **THEN** the response contains only the newest post

#### Scenario: Offset applied
- **WHEN** a client requests `GET /posts?limit=1&offset=1` and two posts exist
- **THEN** the response contains only the older post

#### Scenario: Limit out of range
- **WHEN** a client requests `GET /posts?limit=0` or `GET /posts?limit=101`
- **THEN** the response is 422

### Requirement: Read one post
The API SHALL provide `GET /posts/{run_id}`, which returns the post published by that run, with the same fields as a list item.

#### Scenario: Existing post
- **WHEN** a client requests `GET /posts/{run_id}` for a run that was published
- **THEN** the response is 200 with that run's post

#### Scenario: Run with no post
- **WHEN** a client requests `GET /posts/{run_id}` for an unknown run, or for a run that was not published (rejected, failed, still running)
- **THEN** the response is 404

#### Scenario: Malformed run ID
- **WHEN** a client requests `GET /posts/{run_id}` and the ID is not a valid UUID
- **THEN** the response is 422
