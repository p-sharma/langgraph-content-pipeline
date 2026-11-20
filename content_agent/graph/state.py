import operator
from typing import Annotated, Literal, TypedDict


class SearchResult(TypedDict):
    """A raw search hit, produced by the Searcher."""
    url: str
    title: str
    snippet: str


class RankedSource(SearchResult):
    """A search hit after the Ranker scores it. Inherits url, title, snippet."""
    score: float          # 0-10
    rank_reason: str      # why the Ranker gave this score (shown in the UI)


class Fact(TypedDict):
    """One claim pulled from a source, produced by the Researcher."""
    claim: str
    source_url: str       # every fact must be traceable to a source


# States a node writes. Queued / running / awaiting approval are worked out by the API
# from the checkpoint, because no node runs at those moments.
# "approved" is set by the approval node and replaced by "published" one step later;
# it stays the final value only for runs that ended before the publisher existed.
Status = Literal["approved", "published", "rejected", "failed"]


class ApprovalDecision(TypedDict):
    """The human's answer, passed in with Command(resume=...) to continue a paused run."""
    action: Literal["approve", "request_changes", "reject"]
    feedback: str | None   # required for request_changes; the reason for reject


# ---------- The shared State ----------

class State(TypedDict):
    # Input: set when the run starts
    topic: str
    topic_source: Literal["user", "scout"]
    guidance: str | None

    # Written by agents as the run progresses
    search_queries: list[str]
    search_results: list[SearchResult]    # Searcher
    sources: list[RankedSource]           # Ranker (top 4-5 only)
    facts: Annotated[list[Fact], operator.add]   # research workers append in parallel
    draft: str                            # Writer: text with [n] citation markers
    references: list[str]                 # Writer: references[n-1] is the URL for [n]

    # Critic loop
    critic_notes: Annotated[list[str], operator.add]   # appended, never overwritten
    critic_passed: bool | None            # None = critic could not run (fail open)
    revision_count: int                   # Critic: +1 on each failed review

    # Human approval
    human_feedback: str | None
    status: Status


class ResearchTask(TypedDict):
    """Input for ONE research worker: just what it needs, not the whole State."""
    topic: str
    guidance: str | None
    source: RankedSource