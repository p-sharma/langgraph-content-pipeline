# Design

## Context

See proposal.md for why this change exists, and the two specs for the required behaviour. The current code constrains the approach in these ways:

- `approval` routes itself with `Command[Literal["writer", "__end__"]]`. On approve it returns `Command(update={"status": "approved"}, goto=END)` (`approval.py:80`). `builder.py` adds no edges out of it.
- Graph nodes get their outside clients from lazily cached module functions (`get_llm` in `content_agent/llm.py`, `search_many` in `tools/search.py`), not from state and not from the graph's wiring.
- The API owns one `ConnectionPool` (autocommit, `dict_row`, `prepare_threshold=0`), opened in `lifespan`. It serves both the checkpointer and `api/runs.py`. `DATABASE_URL` and its default are defined only in `api/main.py`.
- `api/status.py` derives status in this order: `runs.error`, then busy set, no checkpoint, interrupts, `next`, `State.status`, and finally failed. `_run_graph` writes any exception from `invoke` to `runs.error`.
- Only `request_changes` writes `human_feedback` (`approval.py:87`). Approve never clears it, so its presence at publish time means "an editor requested changes".
- Notebooks run the graph with `InMemorySaver`, using `thread_id`s that are not necessarily UUIDs, and without a `runs` row.

## Goals / Non-Goals

**Goals:**
- The publisher stays an ordinary node. It doesn't depend on how the API builds or calls the graph, so it also works from a notebook.
- If the publish step runs twice, it doesn't create a second post. That way a later restart-resume can re-run it safely.
- `posts` is a plain read model: the archive endpoints read only this table, never checkpoints.

**Non-Goals:**
- Retrying a failed publish automatically. A failed run stays failed until the restart-resume follow-up exists.
- Sharing one pool between the graph and the API.
- Migrations tooling. The table is created with `CREATE TABLE IF NOT EXISTS`, the same way as `runs`.

## Decisions

### 1. DB access: a lazy `get_pool()` in a new `content_agent/db.py`
`get_pool()` creates and opens a small `ConnectionPool` (max 2) from `DATABASE_URL` the first time it is called, then returns the same pool every time. Its connection settings match the API's pool. `close_pool()` closes it if it was ever opened, and the API's `lifespan` calls it on shutdown. `DATABASE_URL` and its default move into `db.py`, and `api/main.py` imports them from there, so the default is defined once.

`get_pool()` is decorated with `@lru_cache(maxsize=None)`, exactly like `get_llm`, so the code reads the same way as the existing nodes. `close_pool()` closes the cached pool only if one was created (`get_pool.cache_info().currsize`), so shutting down never opens a pool just to close it.

Alternatives considered:
- *Closure in `build_graph(pool)`*: rejected. `build_graph` would need a pool even in notebooks that never publish, and the node would depend on the graph's wiring, unlike every other node.
- *LangGraph runtime `context`*: rejected for now. Every `invoke` would have to pass the pool, and that's more LangGraph machinery to learn before it's needed. If tests later need a fake DB, this is the way to inject one.
- *A lock-guarded global*: rejected for the first iteration. It would fix the rare race listed under Risks, but it adds threading code the project doesn't otherwise need, and that code would be harder to explain in a demo.

### 2. Post SQL in a new top-level module, `content_agent/posts.py`
The module holds the DDL, `PostRow`, `insert_post`, `list_posts` and `get_post`. Each function takes a pool as its first argument, as `api/runs.py` does. The publisher passes `get_pool()`, and the endpoints pass `app.state.pool`.

Alternatives considered:
- *`api/posts.py`*: rejected. The graph would then import from the API package, which reverses the dependency direction.
- *SQL inside `nodes/publisher.py`*: rejected. The API would have to import a graph node module just to read posts.

### 3. Table shape, with `run_id` as primary key
```
posts (
  run_id         text        PRIMARY KEY,
  topic          text        NOT NULL,
  draft          text        NOT NULL,
  "references"   jsonb       NOT NULL,   -- quoted: REFERENCES is a reserved word
  critic_verdict text        NOT NULL,   -- passed | not_reviewed | budget_exhausted
  edited         boolean     NOT NULL,
  published_at   timestamptz NOT NULL DEFAULT now()
)
index on published_at DESC
```
The insert is `INSERT ... ON CONFLICT (run_id) DO NOTHING`. On a replay the existing row, including its original `published_at`, is left as it is.

Alternatives considered:
- *A separate `post_id` with a UNIQUE `run_id`*: rejected. It's a second identifier with no use yet, and the archive URL can use the run ID.
- *`uuid` type with an FK to `runs`*: rejected. Notebook runs have no `runs` row and may use non-UUID thread IDs. The endpoint validates the UUID and passes `str(run_id)`, which has the same lowercase hyphenated form as `runs.run_id::text`.
- *`ON CONFLICT DO UPDATE`*: rejected. A replay would overwrite `published_at`, and the stored post must stay exactly what was approved.

### 4. The publisher reads `run_id` from the run config
`publisher(state, config: RunnableConfig)` reads `config["configurable"]["thread_id"]`. The API already sets `thread_id = run_id` (`main.py:_config`).

Alternative considered: *adding `run_id` to `State`*: rejected. It would duplicate the thread ID, and every caller would have to remember to pass both.

### 5. `critic_verdict` and `edited` are computed at publish time
`approval._critic_verdict` is renamed to a public `critic_verdict` and imported by the publisher, which guarantees the stored verdict matches what the reviewer saw. `edited` is `bool(state.get("human_feedback"))`.

Alternatives considered:
- *Storing the verdict in state during approval*: rejected. It adds a state field whose only job is to carry a value one step forward.
- *Copying the verdict logic into the publisher*: rejected. The two copies could drift apart, and this repeats deferred item 2 (importing private helpers across nodes).

### 6. Routing and status
- On approve, `approval` returns `Command(update={"status": "approved"}, goto="publisher")`. Its return type becomes `Command[Literal["writer", "publisher", "__end__"]]`.
- `builder.py` adds `publisher` and the edge `publisher -> END`.
- The publisher returns `{"status": "published"}`.
- `"published"` is added to `Status` (state.py), `RunStatus.PUBLISHED` (schemas.py) and `END_STATES` (status.py).
- `status.py`'s order does not change. A publisher exception reaches `runs.error`, so the run reports `failed` with the message, as the user confirmed. `approved` is reported only for runs that ended before this change.

Alternative considered: *reporting `approved` when the publish fails*: rejected by the user. It would show a crashed run under a success status.

### 7. Publisher errors are not caught
The node lets exceptions propagate. The checkpoint saved after `approval` has `next=("publisher",)`, so a later `invoke(None)` re-runs only the publisher. Together with decision 3, that makes a retry safe.

Alternative considered: *catching the error and returning `status="failed"`*: rejected. The run would reach END, a retry would no longer be possible, and the error message would be lost.

### 8. Endpoints
`GET /posts?limit=&offset=` and `GET /posts/{run_id}` (`UUID` path parameter, 404 if not found) return a `PostOut` model. Its fields are the table columns, with `references: list[str]`. Both endpoints are sync `def`, like the existing ones. `lifespan` calls `posts.create_table(pool)` next to `runs.create_table`.

Alternative considered: *a summary model for the list, without the draft*: rejected for now. A post is about 200 words, so sending the full text is cheap, and the UI can decide later whether it needs a smaller payload.

### 9. Both pools check connections before handing them out
Added after task 5.2. When Postgres restarted, the API pool still held the connections that the shutdown had killed, and it handed each one out once: 3 requests failed with `AdminShutdown` before the pool had discarded them all. Both `ConnectionPool`s now pass `check=ConnectionPool.check_connection`, so the pool runs a quick check on each connection before lending it and replaces a dead one without failing the request. The same applies to a hosted Postgres that restarts for maintenance.

Alternatives considered:
- *Defer the fix*: rejected by the user, who chose to fix it in this change.
- *Retry failed requests in the endpoints*: rejected. It's more code in every endpoint, and the pool already provides the check.
- *`max_idle`/`max_lifetime` tuning*: rejected. It only shortens the window; a restart can still leave dead connections in the pool.

## Risks / Trade-offs

- [The connection check adds one round trip each time a connection is borrowed] -> Negligible against the LLM calls in a run and at this request rate.

- [The graph pool and the API pool are separate: up to 12 connections] -> The graph pool is capped at 2. This is far below Postgres's default `max_connections` of 100 at this scale.
- [A process crash between `INSERT` and the checkpoint write leaves the run at `next=publisher`, reported as `running`, with the post already stored] -> Decision 3 makes the eventual re-run harmless. Until restart-resume exists, the status is wrong but no data is lost.
- [In a notebook, `posts` doesn't exist unless the API has started once] -> The prototype notebook calls `posts.create_table(get_pool())` explicitly.
- [The graph pool is opened from a worker thread on first publish, so the first publish is slightly slower] -> This is a one-time cost and acceptable.
- [`lru_cache` doesn't lock while `get_pool()` runs. If two runs publish for the first time at the same moment, each may build a pool, and one stays open, unused, until the process exits] -> Accepted for the first iteration. Nothing is stored wrong; the cost is 2 idle connections. If it ever matters, the fix is a lock-guarded global.
- [Older approved runs have no post, so the archive won't show them] -> Accepted. One local run is affected, and it is test data.

## Migration Plan

There is nothing to migrate. Both tables are created when the API starts. To roll back, revert the commit. The `posts` table can be left in place or dropped by hand, since nothing else reads it.
