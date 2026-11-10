from functools import lru_cache

from langchain_tavily import TavilySearch

from content_agent.graph.state import SearchResult


@lru_cache(maxsize=1)
def _get_tool() -> TavilySearch:
    """Create the Tavily client once, the first time it's needed, and reuse it."""
    return TavilySearch(max_results=5, topic="general")


def _normalize_url(url: str) -> str:
    """Treat 'site.com/page/', 'site.com/page' and 'site.com/page#intro' as the same URL."""
    return url.split("#")[0].rstrip("/").lower()


def search_web(query: str) -> list[SearchResult]:
    """Run one search and return results in OUR format."""
    try:
        response = _get_tool().invoke({"query": query})
    except Exception as e:
        print(f"⚠️ Search failed for {query!r}: {e}")
        return []

    if not isinstance(response, dict) or "error" in response:
        print(f"⚠️ Search returned an error for {query!r}: {response}")
        return []

    return [
        SearchResult(
            url=item["url"],
            title=item.get("title", ""),
            snippet=item.get("content", "")[:500],   # keep snippets short
        )
        for item in response.get("results", [])
    ]


def search_many(queries: list[str]) -> list[SearchResult]:
    """Run several searches and merge the results, removing duplicate URLs."""
    seen: set[str] = set()
    combined: list[SearchResult] = []
    for query in queries:
        for result in search_web(query):
            key = _normalize_url(result["url"])
            if key not in seen:
                seen.add(key)
                combined.append(result)
    return combined