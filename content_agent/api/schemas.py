from datetime import datetime
from enum import Enum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunStatus(str, Enum):
    """The full lifecycle. The graph stores only the end states; the API works out the rest."""
    QUEUED = "queued"                        # row created, no checkpoint yet
    RUNNING = "running"                      # graph is between steps
    AWAITING_APPROVAL = "awaiting_approval"  # paused at the approval interrupt
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"                        # no draft, no sources, or the run crashed


# ---------- Requests ----------

class CreateRunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    topic: str = Field(min_length=3, max_length=200)
    guidance: str | None = Field(default=None, max_length=500)


class ResumeRequest(BaseModel):
    """The human's decision. Same shape as the graph's ApprovalDecision."""
    model_config = ConfigDict(str_strip_whitespace=True)

    action: Literal["approve", "request_changes", "reject"]
    feedback: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def feedback_required_for_changes(self) -> Self:
        if self.action == "request_changes" and not self.feedback:
            raise ValueError("feedback is required for request_changes")
        return self


# ---------- Responses ----------

class SourceOut(BaseModel):
    url: str
    title: str
    score: float
    rank_reason: str


class ReviewOut(BaseModel):
    """What the reviewer sees while the run is paused (the interrupt payload)."""
    draft: str
    references: list[str]
    critic_verdict: Literal["passed", "not_reviewed", "budget_exhausted"]
    critic_note: str | None
    revision_count: int
    error: str | None


class RunResponse(BaseModel):
    run_id: str
    topic: str
    guidance: str | None
    status: RunStatus
    created_at: datetime
    error: str | None = None                 # set when the run crashed
    review: ReviewOut | None = None          # set only while awaiting approval
    draft: str | None = None                 # latest draft, in progress or final
    references: list[str] = []
    sources: list[SourceOut] = []
    human_feedback: str | None = None
