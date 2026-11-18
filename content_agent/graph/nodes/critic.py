from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from pydantic import BaseModel, Field

from content_agent.graph.nodes.writer import (
    CITATION_RE,
    _format_facts,
    _group_facts,
    _to_prompt_numbers,
)
from content_agent.graph.prompts import CRITIC_SYSTEM, CRITIC_USER
from content_agent.graph.state import Fact, RankedSource, State
from content_agent.llm import get_structured_llm

MIN_WORDS = 170      # target is ~200; this range is checked in code, not by the LLM
MAX_WORDS = 230
MAX_REVISIONS = 2    # after this many rewrites, send the last draft to approval


# ---------- Schemas ----------

class Issue(BaseModel):
    sentence: str = Field(description="The draft sentence, quoted exactly")
    problem: str = Field(description="What is unsupported or wrong about it")
    fix: str = Field(description="A concrete fix: cite another source, remove, or reword")


class CriticReview(BaseModel):
    issues: list[Issue] = Field(description="Unsupported sentences; empty if every sentence is supported")


# ---------- Checks ----------

def _word_count(draft: str) -> int:
    """Words in the draft, not counting [n] citation markers."""
    return len(CITATION_RE.sub("", draft).split())


def review_draft(
    topic: str,
    draft: str,
    references: list[str],
    sources: list[RankedSource],
    facts: list[Fact],
) -> list[Issue] | None:
    """Ask the LLM which sentences the facts do not support. Returns None if the call fails."""
    # Number sources exactly as the writer's prompt does, and map the draft's
    # citations back to those numbers. Then a fix like "cite [3]" means the same
    # source to the critic and to the writer on its next revision.
    groups = _group_facts(sources, facts)
    urls = [source["url"] for source, _ in groups]

    try:
        llm = get_structured_llm("critic", CriticReview)
        result = llm.invoke([
            SystemMessage(CRITIC_SYSTEM),
            HumanMessage(CRITIC_USER.format(
                topic=topic,
                facts=_format_facts(groups),
                draft=_to_prompt_numbers(draft, references, urls),
            )),
        ])
    except Exception as e:
        print(f"Critic failed: {e}")
        return None
    return result.issues


def _length_ok(words: int) -> bool:
    return MIN_WORDS <= words <= MAX_WORDS


def _format_review(issues: list[Issue], words: int, check_length: bool) -> str:
    """Turn the findings into one note: stored in critic_notes, read by the writer."""
    lines = []
    if check_length and not _length_ok(words):
        lines.append(f"- Length: {words} words. Rewrite to {MIN_WORDS}-{MAX_WORDS} words.")
    for issue in issues:
        lines.append(f'- "{issue.sentence}"\n  Problem: {issue.problem}\n  Fix: {issue.fix}')
    return "\n".join(lines)


# ---------- Node + router ----------

def critic(state: State) -> dict:
    """Graph node: check the draft. Passes only if no sentence is unsupported and length is in range."""
    draft = state.get("draft")
    if not draft:
        print("Critic: no draft to review, ending the run as failed")
        return {"critic_passed": None, "status": "failed"}

    issues = review_draft(
        state["topic"],
        draft,
        state.get("references", []),
        state.get("sources", []),
        state.get("facts", []),
    )
    if issues is None:
        return {"critic_passed": None}   # fail open: end with the unreviewed draft

    words = _word_count(draft)
    # An editor's request (e.g. "cut it to 120 words") overrides the default length range
    check_length = not state.get("human_feedback")
    passed = not issues and (_length_ok(words) or not check_length)
    print(f"Critic: {'passed' if passed else 'failed'} ({len(issues)} issues, {words} words)")

    if passed:
        return {"critic_passed": True, "critic_notes": [f"Passed ({words} words)."]}
    return {
        "critic_passed": False,
        "critic_notes": [_format_review(issues, words, check_length)],
        "revision_count": state.get("revision_count", 0) + 1,
    }


def route_after_critic(state: State) -> str:
    """Routing function: revise on a fail, unless the revision budget is used up.
    Every other outcome goes to the human, except a run with no draft at all."""
    if not state.get("draft"):
        return END                                 # critic already set status="failed"
    if state.get("critic_passed") is not False:   # True (passed) or None (not reviewed)
        return "approval"
    if state.get("revision_count", 0) > MAX_REVISIONS:
        print(f"Critic: still failing after {MAX_REVISIONS} revisions, sending last draft to approval")
        return "approval"
    return "writer"
