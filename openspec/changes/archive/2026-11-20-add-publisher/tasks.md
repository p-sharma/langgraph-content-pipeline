# Tasks

## 1. Prototype

- [x] 1.1 Create `research/publisher.ipynb`. Using a local `ConnectionPool` against the docker-compose DB, create the `posts` table (design decision 3), insert a post built from `research/sample_state.json` with `ON CONFLICT (run_id) DO NOTHING`, insert it a second time, and select it back. Verify that exactly one row exists, its `references` JSONB comes back as a list of strings, and `published_at` did not change on the second insert.

## 2. Shared DB modules

- [x] 2.1 Add `content_agent/db.py`, containing `DATABASE_URL` (moved from `api/main.py` along with its default) and `get_pool()` (`@lru_cache`, like `get_llm`) and `close_pool()` (max 2 connections, the same connection kwargs as the API pool). Check it by importing the module with Postgres stopped: the import must not connect. Then `get_pool() is get_pool()` must be `True`, and after `close_pool()`, calling `close_pool()` again must not fail.
- [x] 2.2 Add `content_agent/posts.py` with `PostRow`, `create_table`, `insert_post` (idempotent), `list_posts(pool, limit, offset)` (newest first) and `get_post(pool, run_id)`. Check it by switching the notebook from 1.1 to these functions: the results must not change, and `get_post` must return `None` for an unknown ID.

## 3. Publisher node and graph wiring

- [x] 3.1 Rename `approval._critic_verdict` to `critic_verdict` and update its call in `_review_request`. Check it by re-running the approval section of `research/approval.ipynb`: the interrupt payload must still show the same `critic_verdict`.
- [x] 3.2 Add `"published"` to `Status` in `content_agent/graph/state.py`. Verify by importing the module.
- [x] 3.3 Add `content_agent/graph/nodes/publisher.py`. `publisher(state, config)` reads `thread_id` from the config, builds the row (draft, references, `critic_verdict(state)`, `edited = bool(human_feedback)`), calls `posts.insert_post(get_pool(), ...)` without catching errors, and returns `{"status": "published"}`. Verify in the notebook by calling the node directly on the sample state with a test config: the row must be stored and the return value must be `{"status": "published"}`.
- [x] 3.4 Route approve to the publisher. In `approval.py`, approve must return `goto="publisher"` and the return type must include `"publisher"`. In `builder.py`, add the `publisher` node and the `publisher -> END` edge. Verify in `research/publisher.ipynb` with `InMemorySaver`, starting from saved research. Approve must end with `status="published"` and one post. Reject must end with `status="rejected"` and no post. Request changes followed by approve must store a post with `edited=True`.
- [x] 3.5 Check replay safety in the notebook. Re-invoke the publisher for a thread that already has a post. Exactly one row must remain and it must be unchanged.

## 4. API

- [x] 4.1 Add `RunStatus.PUBLISHED` to `content_agent/api/schemas.py` and `"published"` to `END_STATES` in `content_agent/api/status.py`. Verify that `derive_status` returns `PUBLISHED` for a snapshot with `status="published"` and no `next`, and still returns `APPROVED` for one with `status="approved"` and no `next`.
- [x] 4.2 In `api/main.py`: import `DATABASE_URL` from `content_agent.db`, call `posts.create_table(pool)` in `lifespan`, and call `close_pool()` at shutdown. Verify that the server starts with `posts` present in `\dt` and shuts down without warnings about an unclosed pool.
- [x] 4.3 Add a `PostOut` model and the endpoints `GET /posts` (`limit` from 1 to 100, default 20; `offset` of 0 or more) and `GET /posts/{run_id}` (UUID, 404 if there's no post). Verify with curl against the post from the notebook. You should get 200 for the list and for the single post, 404 for a random UUID, 422 for `limit=0`, `limit=101` and a non-UUID ID, and an empty list on an empty table.
- [x] 4.4 Make both pools check a connection before handing it out: add `check=ConnectionPool.check_connection` to the API pool in `api/main.py` and the graph pool in `db.py` (design decision 9). Verify with the server running: `docker compose restart postgres`, then the first `GET /runs/{id}` after Postgres is ready must return 200 (it returned 500 three times before the fix).

## 5. End-to-end verification

- [x] 5.1 Live API run: `POST /runs`, wait for `awaiting_approval`, approve through `POST /runs/{id}/resume`, then poll `GET /runs/{id}` until it reports `published`. Check that `GET /posts/{id}` returns the approved draft and references with the right `critic_verdict` and `edited=false`, and that the existing EU AI Act run still reports `approved`.
- [x] 5.2 Failure path: start a second run and let it reach `awaiting_approval`. Then run `docker compose stop postgres` and approve. Note: checkpointing also needs Postgres, so if the resume fails before the publisher runs, record what happened instead of forcing it. Restart Postgres and check that `GET /runs/{id}` reports `failed` with a non-empty `error` and that `GET /posts/{id}` is 404.
  - Outcome (2026-11-20, run `c0c26b88`): with Postgres stopped, `POST /resume` returned 500 from `runs.get_run`, before the graph ran. After the restart the run was unchanged (`awaiting_approval`, no error, no post). The publisher's own failure path ("Publish failure is reported") was not exercised by a live run; the user accepted this. The restart also showed the API pool handing out dead connections (3 requests got 500 before it recovered), which task 4.4 fixes.

## 6. Documentation

- [x] 6.1 Update `README.md`. Make the publisher solid in the mermaid graph (approve -> publisher -> End: published), remove "(the publisher will go here)" from the approval table, add `published` to the State status notes and the API status table, add `GET /posts` and `GET /posts/{id}` to the API table, mark `publisher.py` as built in the project structure, add `db.py` and `posts.py` there too, and add a checked "Publisher" item to the Status checklist. Verify that the mermaid block renders in the VS Code Markdown preview.

## Workflow follow-up

- Work on a feature branch and fast-forward it into main after review. Do not push.
- Archive the change with `openspec-archive-change` once it is merged.
