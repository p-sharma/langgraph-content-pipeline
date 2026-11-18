from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from content_agent.graph.prompts import SEARCHER_SYSTEM, SEARCHER_USER
from content_agent.graph.state import State
from content_agent.llm import get_structured_llm
from content_agent.tools.search import search_many

MAX_QUERIES = 4   # extra queries from the LLM are dropped


class SearchPlan(BaseModel):
    """The shape we force the LLM's answer into."""
    queries: list[str] = Field(
        description=f"3 to {MAX_QUERIES} distinct web search queries, each covering a different angle",
        min_length=1,
    )

def plan_queries(topic: str, guidance: str | None) -> list[str]:
    """Ask the LLM for search queries. Fall back to the plain topic if anything fails."""
    try:
        llm = get_structured_llm("searcher", SearchPlan)
        plan = llm.invoke([
            SystemMessage(SEARCHER_SYSTEM),
            HumanMessage(SEARCHER_USER.format(topic=topic, guidance=guidance or "none"))
        ])
        queries = plan.queries[:MAX_QUERIES]
    except Exception as e:
        print(f"Query planning failed, using topic only: {e}")
        queries = []

    all_queries = [topic] + queries
    unique = list(dict.fromkeys(q.strip() for q in all_queries if q.strip()))
    return unique

def searcher(state: State)-> dict:
    """Graph node: plan queries, run them, store results."""
    queries = plan_queries(state["topic"], state.get("guidance"))
    results = search_many(queries)
    print(f"Searcher: {len(queries)} queries → {len(results)} unique results")
    return {
        "search_queries": queries,
        "search_results": results,
    }