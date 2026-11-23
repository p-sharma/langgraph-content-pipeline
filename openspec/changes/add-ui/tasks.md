# Tasks

## 1. Setup

- [x] 1.1 Create the `add-ui` feature branch from `main` and verify that `git branch --show-current` prints `add-ui`

## 2. Shared helpers

- [x] 2.1 Add `ui/api.py` with `create_run`, `get_run`, `resume_run`, `list_posts` and `get_post` over httpx at `$API_URL`. Raise `ApiError` (carrying the API's `detail`) on connection failure or non-2xx; `get_run`/`get_post` return `None` on 404. Verify from a `python -c` call with the API running: `get_run` of a known ID returns the run, of a random UUID returns `None`, and with the API stopped raises `ApiError`
- [x] 2.2 Add `ui/citations.py` with `render_draft(draft, references)`: `[n]` becomes a markdown link to `references[n-1]`, a marker with no reference stays plain text, and the references come back as a numbered list. Verify from a `python -c` call on a sample draft with `[1]`, `[2]` and an out-of-range `[9]`

## 3. App shell and Run page

- [x] 3.1 Replace `ui/app.py` with the `st.navigation` entry (Run at `/`, Archive at `/archive`), plus `ui/run_page.py` holding the start form (topic of at least 3 chars checked in the UI) and current-run resolution (URL `?run_id=` first, then session; write back to both; unknown ID shows "Run not found"). Verify by running `streamlit run ui/app.py`: starting a run puts its ID in the URL, a refresh shows the same run, and a made-up UUID in the URL shows "Run not found"
- [x] 3.2 Add the live view as an `@st.fragment(run_every=3)` shown while `queued`/`running`, with the status, the stage hint (no sources / sources / draft), sources in an expander and the latest draft rendered with `render_draft`; it calls `st.rerun()` once the status settles. Verify live: the hint and sources change without a reload, and polling stops at `awaiting_approval`
- [x] 3.3 Add the review panel and decision controls for `awaiting_approval`: draft and references, critic verdict and note, revision count, sources expander, feedback box, and Approve / Request changes / Reject buttons calling `resume_run`. Empty feedback on Request changes warns without calling the API, and `ApiError` (409) shows a warning and reruns. Verify live: empty-feedback Request changes is blocked, and a valid one goes back to polling and then to a revised review
- [x] 3.4 Add the end states: `published` shows the post from `get_post` rendered inline, `rejected` and `approved` show a final message, `failed` shows `error`, and any `ApiError` on the page shows `st.error` without crashing. Verify live: an approved run ends showing its post, and with the API stopped the page shows the error message

## 4. Archive page

- [x] 4.1 Add `ui/archive_page.py`: `list_posts(limit=11, offset)` with `offset` in session state, the first 10 shown newest first as expanders (topic, date, critic verdict, edited flag, rendered draft and references), Prev disabled at offset 0, Next enabled only when an 11th row came back, and an empty-state message. Verify live: posts match `GET /posts`, Prev/Next paging works if more than 10 posts exist (or Next stays disabled otherwise), and the empty state shows with no posts

## 5. End-to-end verification and docs

- [x] 5.1 Manual end-to-end run with Postgres, the API and the UI all up: (a) start, then approve, then `published`, and the post appears in the Archive; (b) start, then request changes, then a revised review, then reject, then `rejected`; (c) refresh mid-run and at the review with `?run_id=`, and the same run comes back; (d) switch to Archive and back, and the current run is kept; (e) a stopped API shows an error on both pages. Record the run IDs used
  - (a) `d3a8f5b6-8256-466f-8a3b-b5b51692b4ed` approve -> published, first in Archive; also `b469cacd-0b8e-45d9-bd65-6bf4cd04f1e4` (approved in the browser during 3.3)
  - (b) `eaff2c47-5707-4103-8ee4-916e293c1e6c` empty feedback blocked -> request changes -> revised review (revision_count reset to 0 by design) -> reject -> rejected, not in Archive
  - (a) and (b) clicks were driven through the real UI code with Streamlit AppTest against the live API: browser clicks in that session did not reach the API (cause not found). (c), (d), (e) checked in the browser; (e) also with AppTest (API_URL to an unused port)
- [x] 5.2 Update README.md: the UI section (two pages, `?run_id=` URL, run command), the project tree for the new `ui/` files, and the Status checklist (live run view, approval screen and archive page ticked). Graph diagram, State and API tables are unchanged by this change; check that they still match the code

## Workflow follow-up

- Squash the feature branch to one commit, fast-forward `main`, and do not push.
- Archive the change so `operator-ui` becomes a main spec.
