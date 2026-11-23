# Proposal

## Why

The graph and API now cover the whole Phase 1 flow, from topic to published post, but the only way to drive it is with raw HTTP calls. The Streamlit app can start a run and show its status once, so a human can't watch a run, review its draft, approve it or browse what was published. This UI is the last core piece before deploy.

## What Changes

- Replace the placeholder `ui/app.py` with a two-page Streamlit app built on `st.navigation`: **Run** and **Archive**.
- **Run page:** a topic and guidance form starts a run. The current run's ID lives in the URL (`?run_id=`), so a refresh or a Streamlit restart reopens it.
- **Live run view:** polls `GET /runs/{run_id}` while the run is queued or running. It shows the status, a stage hint inferred from the fields present so far, the sources and the latest draft. Polling stops at any other status.
- **Inline approval:** while the run is `awaiting_approval`, the page shows the review (draft with linked citations, references, critic verdict and note, revision count) and Approve, Request changes and Reject controls that call `POST /runs/{run_id}/resume`. Request changes needs feedback. After any decision the page goes back to polling.
- **End states:** `published` links to the post, `rejected` and `approved` (pre-publisher runs) say so, and `failed` shows the error.
- **Archive page:** lists published posts newest first from `GET /posts`, 10 per page with Prev/Next, each with its draft and linked references.
- A shared citation renderer turns `[n]` markers into links to `references[n-1]` on both pages.
- No API changes. No auth: this is an operator tool for a single user.

Out of scope: listing pending or past runs, editing draft text directly, auth or public access (decided at deploy), and resuming runs interrupted by an API restart.

## Capabilities

### New Capabilities
- `operator-ui`: the operator's web UI for starting a run, following its progress, approving or revising its draft, and browsing the archive of published posts.

### Modified Capabilities
None. The UI uses the existing runs API and `post-archive-api` as they are.

## Impact

- Code: `ui/app.py` is rewritten, and new page modules and a citation helper go under `ui/`. No changes to `content_agent/`.
- APIs: uses existing `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/resume`, `GET /posts` and `GET /posts/{id}`.
- Dependencies: none new. `streamlit>=1.40` and `httpx` are already in `requirements.txt`. The installed Streamlit (1.67) has `st.navigation`, `st.fragment(run_every=...)` and `st.query_params`.
- Load: one GET every 3 s per open run page, against the single-worker API.
- Docs: README UI section and Status checklist.
