import httpx
import trafilatura

HEADERS = {
    # Identify your bot honestly. Some sites block requests with no User-Agent.
    "User-Agent": "Mozilla/5.0 (compatible; ContentAgent/0.1)"
}
MAX_CHARS = 12_000   # ~3k tokens per source: enough for facts, keeps prompts affordable
MIN_CHARS = 200      # less than this is usually a cookie wall or an error page



def fetch_text(url: str, timeout: float = 15.0) -> str | None:
    """Download a page and return its main article text, or None if that fails."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Fetch failed for {url}: {e}")
        return None

    if "html" not in resp.headers.get("content-type", ""):
        print(f"Skipping non-HTML content: {url}")   # PDFs, images, etc.
        return None

    text = trafilatura.extract(resp.text, include_comments=False, include_tables=True)
    if not text or len(text) < MIN_CHARS:
        return None
    return text[:MAX_CHARS]
