# Design

## Context

See proposal.md for the motivation and specs/operator-ui/spec.md for the behaviour.

- The UI talks only to the FastAPI backend at `$API_URL` and never touches Postgres or the graph.
- Status is derived on every `GET /runs/{id}` (`content_agent/api/status.py`), and the response carries the whole run (sources, draft, review, error). So the UI can be a thin view: it holds no state machine of its own, and each poll re-reads the truth.
- `POST /runs/{id}/resume` returns 202 right away. The next GET reports `running` (covered by the in-process active guard) until the graph pauses or ends again.
- The API serves a single uvicorn worker and is synchronous. Polling adds one cheap GET (one row plus one checkpoint read) every few seconds per open run page.
- Streamlit reruns the whole script on every interaction. The installed version (1.67) has `st.navigation`/`st.Page`, `st.fragment(run_every=...)` and `st.query_params`.

## Goals / Non-Goals

**Goals:**
- Each file stays small enough to read in one sitting: one module per page, one for API calls, one for citations.
- No API changes. Every behaviour in the spec comes from fields the API already returns.

**Non-Goals:**
- Automated UI tests (no pytest yet; checked by hand end to end).
- Styling beyond Streamlit defaults.
- Handling several operators at once (two tabs deciding the same run are covered by the API's 409).

## Decisions

### 1. File layout

```
ui/
  app.py           entry: st.navigation([Run, Archive]) and set_page_config
  api.py           httpx calls: create_run, get_run, resume_run, list_posts, get_post
  citations.py     render_draft(draft, references) -> markdown, references list
  run_page.py      form, current-run resolution, polling fragment, review + decision
  archive_page.py  paginated list of posts
```
`streamlit run ui/app.py` puts `ui/` on `sys.path`, so the pages import `api` and `citations` directly with no package setup. `api.py` wraps every call in a single `ApiError` (connection failure or non-2xx, with the API's `detail` when there is one), so each page has one `except` that shows `st.error`. A 404 on `get_run`/`get_post` returns `None` instead, because "not found" is an expected answer, not an error.

*Alternatives:* a single `app.py` with everything (rejected: approval, polling and archive together are too much for one readable file). Streamlit's `pages/` folder convention (rejected: `st.navigation` gives explicit page titles and URL paths in code, and it's the current recommended API).

### 2. Two pages, approval inline (decided in explore)

The Run page holds the form, the live view and the review/decision controls. The Archive page holds the post list. Approval isn't a separate page, because in the API it's a status of the run, not a separate resource.

*Alternatives:* `st.tabs` on one page (rejected: tabs aren't in the URL, and every tab's code runs on every rerun, so the archive would refetch on every poll). Three pages with a separate approval screen (rejected: each status change would mean moving between pages and carrying the run ID along).

### 3. Current run = URL first, session second

On each run of the Run page: `run_id = st.query_params.get("run_id") or st.session_state.get("run_id")`, then write it back to both. Starting a run sets both to the new ID.

The URL covers refresh and restart. The session copy is needed because switching to Archive and back with `st.navigation` drops the query string. An unknown ID (`get_run` returns `None`) shows "Run not found" and clears both.

*Alternatives:* session state only (rejected: lost on refresh, which is the current bug). A `GET /runs` list endpoint (rejected in explore: it adds API scope and a status derivation per row. Deferred as a "pending runs" follow-up).

### 4. Polling: a fragment that reruns the full page when the run settles

```
render_run_page
  |-- form (outside fragment)
  |-- run = get_run(id)
  |-- if run.status in {queued, running}:
  |       live_view(id)   # @st.fragment(run_every=3)
  |          run = get_run(id)
  |          show status, stage hint, sources, draft
  |          if run.status not in {queued, running}: st.rerun()   # full page
  |-- elif awaiting_approval: review + decision controls (no timer)
  |-- else: end state
```
`run_every` is fixed when the fragment is registered, so the fragment can't turn its own timer off. When it sees a settled status it calls `st.rerun()` (whole app), and the page then takes a non-polling branch. That keeps the decision buttons outside any timed fragment, so a click never races a poll. Interval: 3 s (a run takes about a minute, so 3 s feels live while load stays negligible).

*Alternatives:* `time.sleep` + `st.rerun()` loop on the whole page (rejected: it blocks the script, so the form and the navigation stop responding while it sleeps). A manual "Refresh" button (rejected: the spec requires progress without operator action). Server-sent events or websockets (rejected: needs API changes and async, and the API is sync on purpose).

### 5. Stage hint from fields, not from the API

`no sources -> "Searching and ranking sources"`, `sources but no draft -> "Researching sources and drafting"`, `draft -> "Reviewing and revising the draft"`. These come from fields `RunResponse` already has. After request-changes, the draft exists, so the hint correctly reads as revising.

*Alternatives:* adding a `current_node` field to the API (rejected: API scope, and the checkpoint's `next` would leak graph internals into the contract).

### 6. Decisions sent from button callbacks

One `st.text_area` for feedback and three buttons. Request changes checks `feedback.strip()` before calling the API, and shows `st.warning` if it's empty. Each button's handler calls `resume_run`, then `st.rerun()`. The next GET reports `running`, so the page goes back into the polling branch by itself.

A 409 (busy or not awaiting) surfaces as `ApiError`, which turns into `st.warning` plus a rerun. Buttons aren't disabled after a click: the API's busy guard already makes a double click safe, and the warning explains it.

*Alternatives:* disabling buttons with a session flag (rejected: the flag must be cleared correctly on every path, and that's more state for no extra safety). Sending feedback with approve/reject too (rejected: the API ignores it there, so the box applies only to Request changes, and the label says so).

### 7. Citation rendering

`render_draft` swaps each `[n]` for the markdown link `[[n]](references[n-1])` with a single regex, leaving markers with no matching reference as plain text. The numbered references are rendered as a list below. Both pages call it, and the published state on the Run page uses it with the post from `GET /posts/{run_id}`, shown inline.

*Alternatives:* HTML with `unsafe_allow_html` (rejected: not needed for links, and it would render any HTML that ends up in the draft). Footnote-style rendering only, without inline links (rejected: the spec requires linked markers).

### 8. Archive pagination

`offset` lives in `st.session_state` (default 0). The page requests `limit=11`, shows the first 10, and enables Next only when an 11th row came back. That gives "is there a next page" without a count endpoint. Prev is disabled at offset 0. Each post is an `st.expander` titled with the topic and date, showing the verdict, the edited flag and the rendered draft.

*Alternatives:* fetching `limit=10` and always enabling Next (rejected: it leads to an empty last page). Adding a total count to `/posts` (rejected: API change).

## Risks / Trade-offs

- [A draft containing Streamlit markdown specials like `$` (read as LaTeX) or stray `*` renders oddly] → Accepted for now; LLM drafts rarely contain them. Escape them in `render_draft` if it shows up.
- [A run left open in a tab polls forever if the API keeps it in `running`, for example a hung LLM call] → Accepted: the cost is one cheap GET every 3 s. The stuck run itself is the existing "resume interrupted runs" follow-up.
- [Two browser tabs on the same paused run, both clicking] → The API's busy guard and the status check return 409 to the second tab, which shows a warning and reloads.
- [An API restart while a run is `running` leaves it stuck. The UI keeps polling and shows `running`] → Out of scope; the same follow-up as above.
- [No auth: anyone who reaches the UI can start and approve runs] → Fine for a local operator tool. Auth or a public read-only split must be decided before deploy.

## Migration Plan

`ui/app.py` is replaced in place. Run it as before with `streamlit run ui/app.py` (API at `$API_URL`, default `http://localhost:8000`). No data or API changes, so rollback means reverting the commit.
