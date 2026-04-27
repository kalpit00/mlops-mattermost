from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


PolicyAction = Literal["allow", "review", "escalate"]


class ScoreRequest(BaseModel):
    text: str = Field(..., min_length=1)
    channel_type: Optional[str] = None
    prior_violation_count: Optional[int] = None


class ScoreResponse(BaseModel):
    # Keep compatibility with existing Mattermost integration.
    toxicity_score: float
    model_version: str

    # New serving outputs for moderation policy layer.
    policy_action: PolicyAction
    degraded: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool
    model_version: str
