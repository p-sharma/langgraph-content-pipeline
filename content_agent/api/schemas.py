from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

class RunStatus(str, Enum):
    QUEUED = "queued"                        # received, not started yet
    RESEARCHING = "researching"              # agents working (later)
    AWAITING_APPROVAL = "awaiting_approval"  # paused at the human step (later)
    APPROVED = "approved"
    REJECTED = "rejected"

class CreateRunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    topic: str = Field(min_length=3, max_length=200)
    guidance: str | None = Field(default=None, max_length=500)

class RunResponse(BaseModel):
    run_id: str
    topic: str
    guidance: str | None
    status: RunStatus
    created_at: datetime
