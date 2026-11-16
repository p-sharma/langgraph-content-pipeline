from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from content_agent.graph.prompts import RESEARCHER_SYSTEM, RESEARCHER_USER
from content_agent.graph.state import Fact, RankedSource, State, ResearchTask
from content_agent.llm import get_llm
from content_agent.tools.fetch import fetch_text

from langgraph.graph import END
from langgraph.types import Send

MAX_FACTS_PER_SOURCE = 8


class ExtractedFacts(BaseModel):
    facts: list[str] = Field(description="Self-contained factual sentences from the source")


def extract_facts(topic: str, guidance: str | None, source: RankedSource) -> list[Fact]:
    """Fetch one source and extract facts from it."""
    text = fetch_text(source["url"])
    if text is None:
        text = source["snippet"]   # fall back to the search snippet
        print(f"   ↳ using snippet for {source['url']}")

    try:
        llm = get_llm().with_structured_output(ExtractedFacts)
        result = llm.invoke([
            SystemMessage(RESEARCHER_SYSTEM),
            HumanMessage(RESEARCHER_USER.format(
                topic=topic, guidance=guidance or "none", text=text,
            )),
        ])
    except Exception as e:
        print(f"Fact extraction failed for {source['url']}: {e}")
        return []

    # The URL is attached by OUR code, never written by the LLM
    return [
        Fact(claim=claim.strip(), source_url=source["url"])
        for claim in result.facts[:MAX_FACTS_PER_SOURCE]
    ]
  
def research_source(task: ResearchTask) -> dict:
    """Worker node: one instance runs per source, in parallel."""
    facts = extract_facts(task["topic"], task.get("guidance"), task["source"])
    print(f"Worker done: {len(facts)} facts from {task['source']['url']}")
    return {"facts": facts}   # appended to State.facts by the reducer


def fan_out_to_researchers(state: State) -> list[Send] | str:
    """Routing function: create one Send per source."""
    sources = state.get("sources", [])
    if not sources:
        return END   # nothing to research
    return [
        Send("research_source", ResearchTask(
            topic=state["topic"],
            guidance=state.get("guidance"),
            source=source,
        ))
        for source in sources
    ]

def extract_facts(topic: str, guidance: str | None, source: RankedSource) -> list[Fact]:
    """Fetch one source and extract facts from it."""
    text = fetch_text(source["url"])
    if text is None:
        text = source["snippet"]   # fall back to the search snippet
        print(f"   ↳ using snippet for {source['url']}")

    try:
        llm = get_llm().with_structured_output(ExtractedFacts)
        result = llm.invoke([
            SystemMessage(RESEARCHER_SYSTEM),
            HumanMessage(RESEARCHER_USER.format(
                topic=topic, guidance=guidance or "none", text=text,
            )),
        ])
    except Exception as e:
        print(f"⚠️ Fact extraction failed for {source['url']}: {e}")
        return []

    # The URL is attached by OUR code, never written by the LLM
    return [
        Fact(claim=claim.strip(), source_url=source["url"])
        for claim in result.facts[:MAX_FACTS_PER_SOURCE]
    ]
      