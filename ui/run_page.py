"""Run page: start a run, follow it, decide on its draft.

The current run's ID lives in the URL (?run_id=) so a refresh or restart keeps it,
and in session state because switching pages drops the URL's query string.
"""
import streamlit as st

import api
from citations import render_draft

MIN_TOPIC_LENGTH = 3   # same rule as the API's CreateRunRequest
LIVE_STATUSES = {"queued", "running"}   # the page polls only while the run is in one of these
POLL_SECONDS = 3                        # a run takes about a minute: feels live, negligible load


def _stage_hint(run: dict) -> str:
    """The API doesn't say which node is running; what the run has produced so far does."""
    if not run["sources"]:
        return "Searching and ranking sources..."
    if not run["draft"]:
        return "Researching sources and drafting..."
    return "Reviewing and revising the draft..."   # also right after "request changes"


def _set_current(run_id: str | None) -> None:
    """Point both the URL and the session at this run, or clear both."""
    if run_id:
        st.query_params["run_id"] = run_id
        st.session_state["run_id"] = run_id
    else:
        st.query_params.pop("run_id", None)
        st.session_state.pop("run_id", None)


def _current_run_id() -> str | None:
    """The URL wins: a pasted or bookmarked link must open that run, not the last one."""
    run_id = st.query_params.get("run_id") or st.session_state.get("run_id")
    _set_current(run_id)   # e.g. back from Archive: restore ?run_id= from the session
    return run_id


def _start_form() -> None:
    with st.form("new_run"):
        topic = st.text_input("Topic", placeholder="e.g. Rust in the Linux kernel")
        guidance = st.text_area(
            "Guidance (optional)",
            placeholder="e.g. Focus on security implications, for a developer audience",
        )
        submitted = st.form_submit_button("Start research")

    if not submitted:
        return
    if len(topic.strip()) < MIN_TOPIC_LENGTH:
        st.error(f"Please enter a topic of at least {MIN_TOPIC_LENGTH} characters.")
        return
    try:
        run = api.create_run(topic.strip(), guidance.strip() or None)
    except api.ApiError as e:
        st.error(str(e))
        return
    _set_current(run["run_id"])   # the new run replaces whatever was shown


def _show_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for s in sources:
            st.markdown(f"**[{s['title']}](<{s['url']}>)** · score {s['score']:.2f}")
            st.caption(s["rank_reason"])


def _show_progress(run: dict) -> None:
    """Status, stage hint, sources and the latest draft: whatever the run has so far."""
    st.write(f"**Status:** `{run['status']}`")
    if run["status"] in LIVE_STATUSES:
        st.info(_stage_hint(run))
    _show_sources(run["sources"])
    if run["draft"]:
        body, refs = render_draft(run["draft"], run["references"])
        st.markdown(body)
        st.markdown(refs)


@st.fragment(run_every=POLL_SECONDS)
def _live_view(run_id: str) -> None:
    """Reruns on its own every POLL_SECONDS, without rerunning the rest of the page.

    run_every is fixed once the fragment is registered, so the fragment can't stop its
    own timer. Instead, once the run settles it reruns the whole page, and the page
    then takes a branch that doesn't register this fragment.
    """
    try:
        run = api.get_run(run_id)   # fetched here: on timer reruns the args are the original ones
    except api.ApiError as e:
        st.error(str(e))            # keep polling: the next tick may reach the API again
        return
    if run is None or run["status"] not in LIVE_STATUSES:
        st.rerun()                  # scope="app" by default: the full page decides what's next
    _show_progress(run)


def _decide(run_id: str, action: str, feedback: str | None = None) -> None:
    """Send the decision, then rerun the page: the next GET reports `running`, so the
    page goes back to the live view by itself. A 409 (busy, or no longer awaiting
    approval) is kept as a flash, since st.rerun() wipes anything drawn in this pass."""
    try:
        api.resume_run(run_id, action, feedback)
    except api.ApiError as e:
        st.session_state["flash"] = str(e)
    st.rerun()


def _review_panel(run: dict) -> None:
    """The run is paused at approval: show the review and the three decisions."""
    review = run["review"]   # the interrupt payload; always set while awaiting_approval
    st.write(f"**Status:** `{run['status']}`")
    st.write(f"Critic: **{review['critic_verdict']}** · revisions: {review['revision_count']}")
    if review["critic_note"]:
        st.caption(f"Critic note: {review['critic_note']}")
    if review["error"]:
        st.warning(review["error"])

    body, refs = render_draft(review["draft"], review["references"])
    st.markdown(body)
    st.markdown(refs)
    _show_sources(run["sources"])

    run_id = run["run_id"]
    feedback = st.text_area(
        "Feedback (used by Request changes)",
        key=f"feedback_{run_id}",   # per run: text typed for one run never shows on another
    )
    approve, changes, reject = st.columns(3)
    if approve.button("Approve", type="primary", width="stretch"):
        _decide(run_id, "approve")
    if changes.button("Request changes", width="stretch"):
        if feedback.strip():
            _decide(run_id, "request_changes", feedback.strip())
        else:
            st.warning("Write some feedback first: it tells the writer what to change.")
    if reject.button("Reject", width="stretch"):
        _decide(run_id, "reject")


def _show_post(run_id: str) -> None:
    """The stored post, not the run's draft: the post is what readers will see."""
    try:
        post = api.get_post(run_id)
    except api.ApiError as e:
        st.error(str(e))
        return
    if post is None:   # the run reports published but its post row is gone (deleted by hand)
        st.warning("This run was published, but its post no longer exists.")
        return
    published = post["published_at"][:16].replace("T", " ")   # ISO timestamp -> "2026-11-23 18:54"
    edited = " · edited" if post["edited"] else ""
    st.success(f"Published {published}")
    st.caption(f"Critic: {post['critic_verdict']}{edited}")
    body, refs = render_draft(post["draft"], post["references"])
    st.markdown(body)
    st.markdown(refs)


def _end_state(run: dict) -> None:
    """published | rejected | approved | failed: nothing will change any more."""
    status = run["status"]
    if status == "published":
        st.write(f"**Status:** `{status}`")
        _show_post(run["run_id"])
        return
    if status == "rejected":
        st.info("Rejected: nothing was published.")
    elif status == "approved":   # only runs that ended before the publisher existed
        st.success("Approved before publishing existed: nothing was published.")
    else:                        # failed: a crash sets error; no sources or no draft doesn't
        st.error(run["error"] or "The run ended without a draft: no usable sources or facts were found.")
    _show_progress(run)          # what the run produced, for context


def _show_run(run: dict) -> None:
    st.subheader(run["topic"])
    st.caption(f"Run ID: {run['run_id']}")
    if run["status"] in LIVE_STATUSES:
        _live_view(run["run_id"])
    elif run["status"] == "awaiting_approval":
        _review_panel(run)    # outside the fragment: no timer can race a click
    else:
        _end_state(run)


def render() -> None:
    st.title("Content Agent")
    st.caption("Enter a topic. Agents will research it and draft a short summary for your approval.")
    if flash := st.session_state.pop("flash", None):   # set just before an st.rerun()
        st.warning(flash)
    _start_form()

    run_id = _current_run_id()   # after the form, so a run started just now is picked up
    if run_id is None:
        return
    try:
        run = api.get_run(run_id)
    except api.ApiError as e:
        st.error(str(e))
        return
    if run is None:
        st.warning(f"Run not found: {run_id}")
        _set_current(None)
        return
    _show_run(run)
