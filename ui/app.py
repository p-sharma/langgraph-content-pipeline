import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Content Agent", page_icon="📝")
st.title("📝 Content Agent")
st.caption("Enter a topic. Agents will research it and draft a short summary for your approval.")

with st.form("new_run"):
    topic = st.text_input("Topic", placeholder="e.g. Rust in the Linux kernel")
    guidance = st.text_area(
        "Guidance (optional)",
        placeholder="e.g. Focus on security implications, for a developer audience",
    )
    submitted = st.form_submit_button("Start research")

if submitted:
    if len(topic.strip()) < 3:
        st.error("Please enter a topic of at least 3 characters.")
    else:
        try:
            resp = httpx.post(
                f"{API_URL}/runs",
                json={"topic": topic, "guidance": guidance or None},
                timeout=10,
            )
            resp.raise_for_status()
            st.session_state["run_id"] = resp.json()["run_id"]
            st.success("Run started!")
        except httpx.HTTPError as e:
            st.error(f"Could not reach the backend: {e}")

# --- Show the current run ---
if "run_id" in st.session_state:
    run_id = st.session_state["run_id"]
    st.subheader("Current run")
    try:
        run = httpx.get(f"{API_URL}/runs/{run_id}", timeout=10).json()
        st.write(f"**Topic:** {run['topic']}")
        st.write(f"**Status:** `{run['status']}`")
        st.caption(f"Run ID: {run_id}")
    except httpx.HTTPError as e:
        st.error(f"Could not load run: {e}")