from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from content_agent.graph.prompts import RANKER_SYSTEM, RANKER_USER
from content_agent.graph.state import RankedSource, SearchResult, State
from content_agent.llm import get_llm

WEIGHTS = {"relevance": 0.5, "credibility": 0.35, "recency": 0.15}
TOP_K = 5          # how many results to keep
MIN_SCORE = 5.0    # results below this are dropped


class SourceScore(BaseModel):
    index: int = Field(description="The number of the search result")
    relevance: int = Field(ge=0, le=10)
    credibility: int = Field(ge=0, le=10)
    recency: int = Field(ge=0, le=10)
    reason: str = Field(description="One short sentence explaining the scores")


class Ranking(BaseModel):
    scores: list[SourceScore]


def _format_results(results: list[SearchResult]) -> str:
    """Turn results into a numbered list for the prompt."""
    lines = []
    for i, r in enumerate(results):
        lines.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['snippet'][:300]}\n")
    return "\n".join(lines)


def score_results(topic: str, guidance: str | None, results: list[SearchResult]) -> list[RankedSource]:
    """Ask the LLM to score each result, then combine the scores in code."""
    if not results:
        return []

    try:
        llm = get_llm().with_structured_output(Ranking)
        ranking = llm.invoke([
            SystemMessage(RANKER_SYSTEM),
            HumanMessage(RANKER_USER.format(
                today=date.today().isoformat(),
                topic=topic,
                guidance=guidance or "none",
                results=_format_results(results),
            )),
        ])
    except Exception as e:
        print(f"⚠️ Ranking failed, keeping search order: {e}")
        return [
            RankedSource(**r, score=0.0, rank_reason="Ranking unavailable")
            for r in results
        ]

    ranked: list[RankedSource] = []
    seen: set[int] = set()
    for s in ranking.scores:
        if s.index in seen or not (0 <= s.index < len(results)):
            continue   # skip duplicates and indexes that don't exist
        seen.add(s.index)
        final = (
            WEIGHTS["relevance"] * s.relevance
            + WEIGHTS["credibility"] * s.credibility
            + WEIGHTS["recency"] * s.recency
        )
        ranked.append(RankedSource(**results[s.index], score=round(final, 2), rank_reason=s.reason))

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


def ranker(state: State) -> dict:
    """Graph node: score all search results and keep the best ones."""
    ranked = score_results(state["topic"], state.get("guidance"), state.get("search_results", []))

    top = [r for r in ranked if r["score"] >= MIN_SCORE][:TOP_K]
    if not top:
        top = ranked[:3]   # nothing passed the bar: keep the best 3 and let the Critic be strict
    print(f"📊 Ranker: {len(ranked)} scored → kept {len(top)}")
    return {"sources": top}