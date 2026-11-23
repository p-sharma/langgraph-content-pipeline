"""Archive page: published posts, newest first, PAGE_SIZE per page."""
import streamlit as st

import api
from citations import render_draft

PAGE_SIZE = 10
OFFSET_KEY = "archive_offset"   # session state: survives reruns and trips to the Run page


def _move(delta: int) -> None:
    """Button callback: runs before the script reruns, so the new page renders in one pass."""
    st.session_state[OFFSET_KEY] = max(0, st.session_state.get(OFFSET_KEY, 0) + delta)


def _show_post(post: dict) -> None:
    published = post["published_at"][:16].replace("T", " ")   # ISO timestamp -> "2026-11-23 18:54"
    with st.expander(f"{post['topic']} · {published}"):
        edited = " · edited" if post["edited"] else ""
        st.caption(f"Critic: {post['critic_verdict']}{edited} · run {post['run_id']}")
        body, refs = render_draft(post["draft"], post["references"])
        st.markdown(body)
        st.markdown(refs)


def render() -> None:
    st.title("Archive")
    st.caption("Published posts, newest first.")

    offset = st.session_state.get(OFFSET_KEY, 0)
    try:
        # One extra row answers "is there a next page?" without a count endpoint
        posts = api.list_posts(limit=PAGE_SIZE + 1, offset=offset)
    except api.ApiError as e:
        st.error(str(e))
        return
    has_next = len(posts) > PAGE_SIZE
    posts = posts[:PAGE_SIZE]

    if not posts:
        # offset > 0 with nothing here: posts were deleted since we paged forward
        st.info("No published posts yet." if offset == 0 else "No posts on this page.")
    for post in posts:
        _show_post(post)

    prev, page, nxt = st.columns([1, 2, 1])
    prev.button("< Prev", on_click=_move, args=(-PAGE_SIZE,), disabled=offset == 0, width="stretch")
    page.caption(f"Page {offset // PAGE_SIZE + 1}")
    nxt.button("Next >", on_click=_move, args=(PAGE_SIZE,), disabled=not has_next, width="stretch")
