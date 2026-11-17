import re

from langchain_core.messages import HumanMessage, SystemMessage

from content_agent.graph.prompts import WRITER_REVISION, WRITER_SYSTEM, WRITER_USER
from content_agent.graph.state import Fact, RankedSource, State
from content_agent.llm import get_llm

# Matches " [3]" and " [1, 3]", including the space before it, so removed citations leave no gap.
CITATION_RE = re.compile(r"(\s*)\[(\d+(?:\s*,\s*\d+)*)\]")


def _group_facts(sources: list[RankedSource], facts: list[Fact]) -> list[tuple[RankedSource, list[str]]]:
    """Pair each source with its facts, in rank order. Sources with no facts are skipped."""
    claims_by_url: dict[str, list[str]] = {}
    for fact in facts:
        claims_by_url.setdefault(fact["source_url"], []).append(fact["claim"])
    return [(s, claims_by_url[s["url"]]) for s in sources if s["url"] in claims_by_url]


def _format_facts(groups: list[tuple[RankedSource, list[str]]]) -> str:
    """Render groups as a numbered list for the prompt: [1] Title, then its facts."""
    blocks = []
    for i, (source, claims) in enumerate(groups, start=1):
        lines = [f"[{i}] {source['title']}"] + [f"- {c}" for c in claims]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _renumber_citations(text: str, urls: list[str]) -> tuple[str, list[str]]:
    """Renumber [n] markers by first appearance and drop invalid ones.

    `urls[i]` is the URL for prompt number i+1. Returns the cleaned text and the
    references list, where references[n-1] is the URL for the new [n].
    """
    new_number: dict[int, int] = {}   # prompt number -> number in the final text
    references: list[str] = []

    def replace(match: re.Match) -> str:
        space, inner = match.group(1), match.group(2)
        cites = []
        for part in inner.split(","):
            n = int(part)
            if not 1 <= n <= len(urls):
                continue                       # the LLM cited a source that doesn't exist
            if n not in new_number:
                references.append(urls[n - 1])
                new_number[n] = len(references)
            cites.append(f"[{new_number[n]}]")
        return space + "".join(dict.fromkeys(cites)) if cites else ""

    return CITATION_RE.sub(replace, text), references


def _to_prompt_numbers(draft: str, references: list[str], urls: list[str]) -> str:
    """Map a stored draft's [n] markers back to prompt numbers, for a revision prompt."""
    def replace(match: re.Match) -> str:
        cites = []
        for part in match.group(2).split(","):
            n = int(part)
            if 1 <= n <= len(references) and references[n - 1] in urls:
                cites.append(f"[{urls.index(references[n - 1]) + 1}]")
        return match.group(1) + "".join(cites) if cites else ""

    return CITATION_RE.sub(replace, draft)


def write_draft(
    topic: str,
    guidance: str | None,
    sources: list[RankedSource],
    facts: list[Fact],
    previous_draft: str | None = None,
    previous_references: list[str] | None = None,
    feedback: str | None = None,
) -> tuple[str, list[str]] | None:
    """Write (or revise) the summary. Returns (draft, references), or None if the LLM call fails."""
    groups = _group_facts(sources, facts)
    if not groups:
        print("Writer: no facts to write from, skipping")
        return "", []
    urls = [source["url"] for source, _ in groups]

    revision = ""
    if previous_draft and feedback:
        revision = WRITER_REVISION.format(
            draft=_to_prompt_numbers(previous_draft, previous_references or [], urls),
            feedback=feedback,
        )

    try:
        response = get_llm("writer").invoke([
            SystemMessage(WRITER_SYSTEM),
            HumanMessage(WRITER_USER.format(
                topic=topic,
                guidance=guidance or "none",
                facts=_format_facts(groups),
                revision=revision,
            )),
        ])
    except Exception as e:
        print(f"Writer failed: {e}")
        return None

    return _renumber_citations(response.text.strip(), urls)


def _revision_feedback(state: State) -> str | None:
    """Collect the feedback the next draft must address."""
    parts = []
    if state.get("critic_passed") is False and state.get("critic_notes"):
        parts.append(f"Reviewer: {state['critic_notes'][-1]}")
    if state.get("human_feedback"):
        parts.append(f"Editor: {state['human_feedback']}")
    return "\n".join(parts) or None


def writer(state: State) -> dict:
    """Graph node: write the first draft, or revise the existing one using feedback."""
    result = write_draft(
        state["topic"],
        state.get("guidance"),
        state.get("sources", []),
        state.get("facts", []),
        previous_draft=state.get("draft"),
        previous_references=state.get("references"),
        feedback=_revision_feedback(state),
    )
    if result is None:
        return {}   # no update: whatever draft the State already has is kept
    draft, references = result
    print(f"Writer: {len(draft.split())} words, {len(references)} sources cited")
    return {"draft": draft, "references": references}
