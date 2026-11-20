# Proposal

## Why

An approved draft goes nowhere: the approval node ends the run with `status="approved"`, and the text only lives in the checkpoint. Phase 1 promises "approve, then publish (saved to Postgres and shown on an archive page)". The UI's archive screen and the deploy both need published posts to exist first, so the publisher is the next step in the core flow.

## What Changes

- New `publisher` graph node, placed after approval. It writes the approved draft to a new `posts` table and sets `status="published"`.
- On approve, the approval node still sets `status="approved"`, but now routes to `publisher` instead of `END`.
- `"published"` is added to `State.status`, to the API's `RunStatus`, and to the end states the API recognises.
- New `posts` table. It has one row per published run, keyed by `run_id`. The insert can be replayed safely: if the node re-runs after a crash, it does not create a second row.
- New lazily created connection pool for graph nodes (`get_pool()` from `DATABASE_URL`), following the `get_llm()` pattern. It lets the node reach Postgres without the API passing anything in.
- New read endpoints: `GET /posts` (newest first) and `GET /posts/{run_id}`.
- Out of scope: external platforms and social posting (Phase 3), editing or unpublishing a post, and automatically resuming runs that a restart interrupted.

## Capabilities

### New Capabilities
- `content-publishing`: how an approved run becomes a stored post. This covers the publisher's place in the graph, the run's statuses on the way, what a post records, and safe replay.
- `post-archive-api`: the HTTP read access to published posts that the archive page uses.

### Modified Capabilities

None. `openspec/specs/` is empty: the existing graph and runs API were built before OpenSpec was adopted.

## Impact

- Graph: `content_agent/graph/state.py` (`Status`), `content_agent/graph/nodes/approval.py` (the approve route and its return type), the new `content_agent/graph/nodes/publisher.py`, and `content_agent/graph/builder.py` (the new node and its edge to `END`).
- Database: a new `posts` table. A new module shared by the publisher and the API holds the table's SQL, and another new module provides `get_pool()`.
- API: `content_agent/api/schemas.py` (`RunStatus.PUBLISHED` and the post response models), `content_agent/api/status.py` (`END_STATES`), and `content_agent/api/main.py` (creating the table at startup, closing the graph pool at shutdown, the two endpoints).
- Behaviour visible to users: a newly approved run now finishes as `published`, not `approved`. Runs approved before this change, such as the EU AI Act run in the local DB, still report `approved` and have no post.
- No new dependencies. `psycopg` and `psycopg_pool` are already used.
