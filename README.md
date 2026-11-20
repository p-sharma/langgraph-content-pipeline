# Automated Content Creation (multi-agent, LangGraph)

A multi-agent pipeline built with **LangGraph**. The user enters a topic. Agents search the web, rank the sources, research the topic and write a short (~200-word) summary with citations. A critic agent fact-checks the draft, and a human approves it before it is published.

This is a portfolio project meant to be deployed and shown, not a toy demo.

## Phases

| Phase | Scope |
|---|---|
| **Phase 1 (MVP)** | User enters a topic → search → rank → research → write → critic loop → **human approval** → publish (saved to Postgres and shown on an archive page) |
| Phase 2 | **Trend Scout** agent finds trending topics from Google Trends RSS, Hacker News, Wikipedia pageviews and Reddit; the human picks one or enters their own (first human-in-the-loop checkpoint) |
| Phase 3 (stretch) | Scheduled daily runs, short video generation (script → TTS → video), social posting, evals dashboard |

## Phase 1 graph

```mermaid
flowchart TD
    START([User enters topic + optional guidance]) --> SEARCH[searcher<br/>topic + 3-4 LLM queries via Tavily<br/>deduplicated results]
    SEARCH --> RANK[ranker<br/>scores relevance, credibility, recency<br/>keeps top 5 with reasons]
    RANK -- "no sources" --> NOSRC([End: nothing to research])
    RANK -- "Send() x one per source" --> R1[research_source]
    RANK --> R2[research_source]
    RANK --> R3[research_source]
    R1 & R2 & R3 -- "facts merged by<br/>operator.add reducer" --> WRITE[writer<br/>~200-word summary<br/>citations renumbered to references]
    WRITE --> CRITIC{critic<br/>every claim supported by cited facts?<br/>170-230 words?}
    CRITIC -- "fail: issues fed back<br/>(max 2 revisions)" --> WRITE
    CRITIC -- "no draft" --> FAILED([End: failed])
    CRITIC -- "pass, not reviewed,<br/>or budget used up" --> APPROVAL{{approval<br/>interrupt: pause for a human}}
    APPROVAL -- "request changes (feedback)<br/>fresh critic budget" --> WRITE
    APPROVAL -- reject --> REJECTED([End: rejected, reason in human_feedback])
    APPROVAL -- "approve<br/>status=approved" --> PUBLISH[publisher<br/>store the post in Postgres<br/>one row per run]
    PUBLISH --> DONE([End: published])
```

The **critic loop** is the graph's first cycle. `route_after_critic` returns `"writer"` on a fail, sending the draft back with the critic's notes as revision feedback, and `"approval"` otherwise, so a pass, a skipped review (`critic_passed=None`, fail open) and a used-up budget (after 2 revisions) all reach a human. Only a run with no draft at all ends early, with `status="failed"`. Pass/fail is decided in code: the LLM only lists unsupported sentences (quote, problem, fix), and the word count (170-230) is checked deterministically. The length check is skipped while an editor's feedback is set, so a request like "cut it to 120 words" is not undone by the critic.

The research step is a **map-reduce fan-out**: `fan_out_to_researchers` returns one `Send("research_source", ResearchTask)` per ranked source, so the workers run in parallel and each one sees only its own source. Each worker returns `{"facts": [...]}`, and the `operator.add` reducer on `State.facts` concatenates the results instead of letting the last worker overwrite the others.

The **approval** node uses LangGraph `interrupt()`. The graph pauses and its state is saved by the checkpointer (`InMemorySaver` in notebooks, `PostgresSaver` in the API, so a paused run survives a server restart). The reviewer sees the draft, references, the critic's verdict (`passed`, `not_reviewed` or `budget_exhausted`) and, when the budget ran out, the critic's unresolved issues. The run resumes with `Command(resume={"action": ..., "feedback": ...})`:

| Action | Effect |
|---|---|
| `approve` | `status="approved"`, then the publisher |
| `request_changes` | feedback (required) goes to the writer; `revision_count` resets so the rewrite gets a fresh critic budget |
| `reject` | `status="rejected"`, the reason is kept in `human_feedback`, end |

The node routes itself by returning `Command(update=..., goto=...)`; its `Command[Literal["writer", "publisher", "__end__"]]` return type tells LangGraph the possible targets, so `builder.py` adds no edges out of it. An invalid decision does not raise: the node calls `interrupt()` again with an `error` in the payload, and the run stays paused. On resume LangGraph re-runs the node from the top, so nothing before `interrupt()` has side effects. [research/approval.ipynb](research/approval.ipynb) walks through approve, request changes and reject, starting from saved research.

The **publisher** stores the approved draft in the `posts` table and sets `status="published"`. A post holds the topic, the draft with its citation markers, the references, the critic's verdict (the same one the reviewer saw), whether an editor requested changes (`edited`), and `published_at`. The node takes a second parameter, `config`, which LangGraph fills with the run's config; its `thread_id` is the run ID, so no extra State field is needed. It gets its database connection from `db.get_pool()`, a small pool created on first use, the same way nodes get their LLM from `get_llm()`.

Publishing is safe to repeat: `run_id` is the table's primary key and the insert uses `ON CONFLICT DO NOTHING`, so if the publisher runs twice for one run (for example, retried after a crash), the second insert leaves the stored post unchanged. Errors are not caught: a failed insert stops the run with its last checkpoint saying "publisher is next", so it can be retried, and the API reports it as `failed` with the error. [research/publisher.ipynb](research/publisher.ipynb) prototypes the table and checks each step: approve, reject, request changes then approve, and a replay.

## Shared state

Defined in [content_agent/graph/state.py](content_agent/graph/state.py):

```python
class State(TypedDict):
    # Input
    topic: str
    topic_source: Literal["user", "scout"]   # "scout" used in phase 2
    guidance: str | None                     # optional angle / audience note

    # Written by agents
    search_queries: list[str]
    search_results: list[SearchResult]       # searcher: url, title, snippet
    sources: list[RankedSource]              # ranker: + score, rank_reason (top 5)
    facts: Annotated[list[Fact], operator.add]   # research workers append in parallel
    draft: str                               # writer: text with [n] citation markers
    references: list[str]                    # writer: references[n-1] is the URL for [n]

    # Critic loop
    critic_notes: Annotated[list[str], operator.add]   # appended, never overwritten
    critic_passed: bool | None               # None = critic could not run
    revision_count: int

    # Human approval
    human_feedback: str | None
    status: Literal["approved", "published", "rejected", "failed"]
```

`ResearchTask` (topic, guidance, one `RankedSource`) is the private input each `research_source` worker receives through `Send`; it is not part of `State`. Likewise `ApprovalDecision` (`action`, `feedback`) is the resume value the approval node reads; only its effects are written to `State`. `status` holds only values a node writes, because a node can only write a value while it runs; queued, running and awaiting approval are worked out by the API (see below). `approved` is set by the approval node and replaced by `published` one step later; it stays the final value only for runs that ended before the publisher existed.

## Project structure

```
AutomatedContentCreation/
├── requirements.txt          # runtime dependencies
├── requirements-dev.txt      # dev tools (pytest, ruff, ipykernel, python-dotenv)
├── .env                      # API keys (git-ignored, see Setup)
├── docker-compose.yml        # local Postgres
├── .vscode/settings.json     # notebooks run from the project root
├── research/                 # notebooks + sample JSON: experiments before code moves into modules
│   ├── explore.ipynb
│   ├── search.ipynb / searcher.ipynb / ranker.ipynb / researcher.ipynb
│   ├── approval.ipynb        # interrupt + resume: approve, request changes, reject
│   ├── publisher.ipynb       # posts table prototype, publisher node, approve / reject / replay checks
│   └── sample_search.json, sample_state.json
├── content_agent/
│   ├── llm.py                # get_llm(role) / get_structured_llm(role, schema), per-role model via env
│   ├── db.py                 # DATABASE_URL, get_pool() / close_pool(): the graph's own small pool
│   ├── posts.py              # posts table: create, insert (safe to repeat), list, get
│   ├── graph/
│   │   ├── state.py          # State, SearchResult, RankedSource, Fact, ResearchTask, ApprovalDecision
│   │   ├── prompts.py        # all LLM prompts
│   │   ├── builder.py        # wires nodes + edges into the graph
│   │   └── nodes/
│   │       ├── searcher.py   # plans queries, runs Tavily, deduplicates
│   │       ├── ranker.py     # scores and keeps top 5
│   │       ├── researcher.py # Send fan-out + per-source fact extraction
│   │       ├── writer.py     # draft + citation renumbering, revision prompt
│   │       ├── critic.py     # support + length check, routes to writer / approval / END
│   │       ├── approval.py   # human-in-the-loop interrupt, routes with Command
│   │       └── publisher.py  # stores the approved draft as a post, status="published"
│   ├── tools/
│   │   ├── search.py         # Tavily wrapper
│   │   └── fetch.py          # httpx + trafilatura page text extraction
│   └── api/
│       ├── main.py           # FastAPI app: lifespan (pool, checkpointer, graph, executor), endpoints
│       ├── schemas.py        # request/response models, RunStatus
│       ├── runs.py           # runs table: one row per run (no status column)
│       ├── status.py         # status worked out from the runs row + graph checkpoint
│       └── active.py         # run IDs with a graph.invoke in progress (busy guard)
├── ui/
│   └── app.py                # Streamlit UI: topic form, calls the API at $API_URL
└── tests/                    # (planned)
```

## Tech stack

- **LangGraph**: agent orchestration, conditional edges, interrupts
- **LangChain** (`init_chat_model`) with Anthropic Claude: LLM calls; structured output uses native JSON schema (`method="json_schema"`). Provider and model are set per role via `LLM_MODEL_<ROLE>` / `LLM_MODEL`
- **Tavily**: web search; **httpx + trafilatura**: page fetching and text extraction
- **Postgres** + `langgraph-checkpoint-postgres`: durable graph state
- **FastAPI + Uvicorn**: API
- **Streamlit**: minimal UI
- **LangSmith**: tracing / observability

## Setup (pip)

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
docker compose up -d                   # start Postgres
```

Create `.env` in the project root with `ANTHROPIC_API_KEY` and `TAVILY_API_KEY`. Optional: `LLM_MODEL` or `LLM_MODEL_<ROLE>` (e.g. `LLM_MODEL_WRITER`) to override the default model, `LANGSMITH_*` for tracing, and `DATABASE_URL` (defaults to the docker-compose database, `postgresql://agent:agent@localhost:5432/content_agent`).

Run commands from the project root:

```bash
uvicorn content_agent.api.main:app --env-file .env --reload   # API on :8000 (fails at startup if Postgres is down)
streamlit run ui/app.py                                       # UI (API_URL defaults to http://localhost:8000)
```

`--reload` restarts the server on every file save, which stops runs that are in progress (see Known limitations).

## API

| Method | Endpoint | Purpose | Responses |
|---|---|---|---|
| POST | `/runs` | Start a run with `{topic, guidance}`; the graph runs in the background | 201, 422 |
| GET | `/runs/{id}` | Status, draft, references, sources, feedback; `review` while awaiting approval | 200, 404, 422 |
| POST | `/runs/{id}/resume` | `{action, feedback}`: `approve` / `request_changes` (feedback required) / `reject` | 202, 404, 409 (busy or not awaiting approval), 422 |
| GET | `/posts` | Published posts, newest first; `limit` (1-100, default 20), `offset` (default 0) | 200, 422 |
| GET | `/posts/{id}` | The post a run published (`id` is the run ID) | 200, 404 (unknown or not published), 422 |

The run ID is the graph's `thread_id`. Startup (FastAPI `lifespan`) opens one psycopg `ConnectionPool` (`autocommit`, `dict_row`, `prepare_threshold=0`, as `PostgresSaver` requires), runs `checkpointer.setup()`, creates the `runs` and `posts` tables and builds the graph once. The publisher node uses its own small pool from `db.get_pool()`, which shutdown closes. Both pools check each connection before lending it (`check=ConnectionPool.check_connection`), so a Postgres restart doesn't fail the next requests. Runs execute on a dedicated `ThreadPoolExecutor` (4 at a time; extra runs wait in its queue), so long LLM calls never hold the threads that serve requests.

**Status is never stored**; `GET` works it out on every call, in this order:

| Condition | Status |
|---|---|
| the background run crashed (`runs.error` is set) | `failed` |
| a `graph.invoke` for this run is in progress in this process | `running` |
| no checkpoint yet | `queued` |
| the checkpoint has a pending interrupt | `awaiting_approval` |
| the checkpoint has a next node | `running` |
| finished: `State.status` | `published` / `rejected` / `failed` (`approved` only for runs from before the publisher) |
| finished without an end state (e.g. no sources) | `failed` |

### Known limitations

- **Single uvicorn worker only.** The busy guard that turns a double-clicked resume into a 409 is in-process memory.
- **A restart in the middle of a run leaves it reporting `running`.** Its checkpoint still has a next node, but nothing is executing it. Runs paused at approval are not affected and resume normally. The fix is to resume these runs with `invoke(None)` at startup.

## Status

- [x] Project structure and dependencies
- [x] Local env + VS Code notebook setup
- [x] `state.py`: State schema
- [x] Tools: search + fetch (prototyped in `research/` notebooks)
- [x] Nodes: searcher → ranker → researcher (parallel `Send`) → writer
- [x] `llm.py`: per-role models, native JSON-schema structured output
- [ ] Researcher prompt: stop meta-facts ("the source does not state...")
- [x] Critic node + revision loop
- [x] `failed` status for no-draft runs
- [ ] `failed` status for no-sources runs in the graph (the API already reports them as `failed`)
- [x] Human approval interrupt (approve / request changes / reject), tested with `InMemorySaver`
- [x] Postgres checkpointer (paused runs survive a server restart)
- [x] FastAPI endpoints wired to the graph: `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/resume`
- [x] Publisher: approved drafts stored in the `posts` table (safe to repeat), `GET /posts`, `GET /posts/{id}`
- [ ] Resume runs interrupted by a restart, at startup
- [ ] Minimal UI: topic input (done), live run view, approval screen
- [ ] Deploy
