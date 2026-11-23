"""Streamlit entry point: `streamlit run ui/app.py`. Holds only the page list.

Streamlit puts this file's folder (ui/) on sys.path, so the page modules and
their helpers (api, citations) import by plain name.
"""
import streamlit as st

import archive_page
import run_page

st.set_page_config(page_title="Content Agent")

nav = st.navigation([
    st.Page(run_page.render, title="Run", url_path="run", default=True),   # default: served at /
    st.Page(archive_page.render, title="Archive", url_path="archive"),
])
nav.run()
