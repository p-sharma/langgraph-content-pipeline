"""Every call the UI makes to the Content Agent API.

Pages import these functions and never use httpx themselves, so there is one place
that knows the URLs, the timeout and how errors look.
"""
import os

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 10   # seconds; every endpoint returns quickly (runs execute in the background)


class ApiError(Exception):
    """The API could not be reached or answered with an error. str(e) is ready to show."""


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        return httpx.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as e:   # connection refused, timeout, DNS ...
        raise ApiError(f"Could not reach the API at {API_URL}: {e}") from e


def _json(resp: httpx.Response):
    """The response body, or ApiError with the API's own explanation."""
    if resp.is_success:
        return resp.json()
    try:
        detail = resp.json().get("detail")
    except ValueError:             # not JSON, e.g. a proxy's HTML error page
        detail = None
    if isinstance(detail, list):   # FastAPI 422: a list of validation errors
        detail = detail[0].get("msg")
    raise ApiError(f"API error {resp.status_code}: {detail or resp.text}")


# ---------- Runs ----------

def create_run(topic: str, guidance: str | None) -> dict:
    return _json(_request("POST", "/runs", json={"topic": topic, "guidance": guidance}))


def get_run(run_id: str) -> dict | None:
    """None if the run doesn't exist. A malformed ID (422) counts as not found:
    it can only come from a hand-edited URL."""
    resp = _request("GET", f"/runs/{run_id}")
    if resp.status_code in (404, 422):
        return None
    return _json(resp)


def resume_run(run_id: str, action: str, feedback: str | None = None) -> dict:
    """action: approve | request_changes | reject. 409 (busy / not awaiting) raises ApiError."""
    return _json(_request("POST", f"/runs/{run_id}/resume", json={"action": action, "feedback": feedback}))


# ---------- Posts ----------

def list_posts(limit: int, offset: int) -> list[dict]:
    return _json(_request("GET", "/posts", params={"limit": limit, "offset": offset}))


def get_post(run_id: str) -> dict | None:
    """None if the run published nothing."""
    resp = _request("GET", f"/posts/{run_id}")
    if resp.status_code == 404:
        return None
    return _json(resp)
