from typing import Literal

from langgraph.graph import END
from langgraph.types import Command, interrupt

from content_agent.graph.state import ApprovalDecision, State

ACTIONS = ("approve", "request_changes", "reject")


# ---------- What the human sees ----------

def critic_verdict(state: State) -> str:
    """Why this draft reached the human: it passed, it was not reviewed, or the critic gave up.

    Public: the publisher stores this same verdict with the post.
    """
    passed = state.get("critic_passed")
    if passed is True:
        return "passed"
    if passed is None:
        return "not_reviewed"
    return "budget_exhausted"


def _review_request(state: State) -> dict:
    """The interrupt payload. Plain JSON: it is saved in the checkpoint and sent by the API."""
    verdict = critic_verdict(state)
    notes = state.get("critic_notes", [])
    return {
        "draft": state["draft"],
        "references": state.get("references", []),
        "critic_verdict": verdict,
        # The unresolved issues, so the reviewer knows what the critic still objects to
        "critic_note": notes[-1] if verdict == "budget_exhausted" and notes else None,
        "revision_count": state.get("revision_count", 0),
        "error": None,
    }


# ---------- Checking the answer ----------

def _clean_feedback(decision: ApprovalDecision) -> str | None:
    feedback = decision.get("feedback")
    if isinstance(feedback, str) and feedback.strip():
        return feedback.strip()
    return None


def _validation_error(decision: object) -> str | None:
    """Why the decision cannot be used, or None if it is valid."""
    if not isinstance(decision, dict):
        return "The decision must be an object with 'action' and 'feedback'."
    if decision.get("action") not in ACTIONS:
        return f"Unknown action {decision.get('action')!r}. Use one of: {', '.join(ACTIONS)}."
    if decision["action"] == "request_changes" and _clean_feedback(decision) is None:
        return "request_changes needs feedback: say what the writer should change."
    return None


# ---------- Node ----------

def approval(state: State) -> Command[Literal["writer", "publisher", "__end__"]]:
    """Graph node: pause for a human decision, then route on it.

    On resume, LangGraph runs this node again from the top and each interrupt()
    call returns its resume value instead of pausing. Nothing before the last
    interrupt() may have side effects (including print), or it runs twice.
    """
    request = _review_request(state)
    while True:
        decision = interrupt(request)
        error = _validation_error(decision)
        if error is None:
            break
        request = {**request, "error": error}   # ask again; the run stays paused, not failed

    action = decision["action"]
    feedback = _clean_feedback(decision)
    print(f"Approval: {action}" + (f" ({feedback})" if feedback else ""))

    if action == "approve":
        return Command(update={"status": "approved"}, goto="publisher")
    if action == "reject":
        return Command(update={"status": "rejected", "human_feedback": feedback}, goto=END)

    # request_changes: rewrite from the editor's note, then a fresh critic budget
    return Command(
        update={
            "human_feedback": feedback,
            "critic_passed": None,   # the writer then uses only the editor's note, not a stale critic note
            "revision_count": 0,
        },
        goto="writer",
    )
