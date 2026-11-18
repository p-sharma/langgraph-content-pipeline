"""Turn a runs row + a graph checkpoint into what the API reports.

Pure functions: no database or graph calls, so they can be tested with plain objects.
"""
from langgraph.types import StateSnapshot

from content_agent.api.runs import RunRow
from content_agent.api.schemas import RunResponse, RunStatus

END_STATES = {"approved", "rejected", "failed"}   # the values State.status can hold


def derive_status(row: RunRow, snapshot: StateSnapshot, active: bool) -> RunStatus:
    """Order matters: each check assumes the ones above it did not match.

    `active` means a graph.invoke for this run is in progress in this process.
    """
    if row["error"]:
        return RunStatus.FAILED                 # the background run crashed
    if active:
        return RunStatus.RUNNING                # covers the gaps the checkpoint lags behind
    if snapshot.created_at is None:
        return RunStatus.QUEUED                 # no checkpoint written yet
    if snapshot.interrupts:
        return RunStatus.AWAITING_APPROVAL      # paused inside the approval node
    if snapshot.next:
        return RunStatus.RUNNING                # more steps to run
    status = snapshot.values.get("status")
    if status in END_STATES:
        return RunStatus(status)
    return RunStatus.FAILED                     # finished without an end state (e.g. no sources)


def to_response(row: RunRow, snapshot: StateSnapshot, active: bool) -> RunResponse:
    status = derive_status(row, snapshot, active)
    values = snapshot.values
    review = snapshot.interrupts[0].value if status == RunStatus.AWAITING_APPROVAL else None
    return RunResponse(
        **row,
        status=status,
        review=review,
        draft=values.get("draft") or None,      # "" (writer had no facts) reads as no draft
        references=values.get("references", []),
        sources=values.get("sources", []),      # extra keys (snippet) are dropped by SourceOut
        human_feedback=values.get("human_feedback"),
    )
