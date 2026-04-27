from __future__ import annotations

import os
from dataclasses import dataclass

from .schemas import PolicyAction


@dataclass(frozen=True)
class PolicyConfig:
    review_threshold: float = 0.70
    escalate_threshold: float = 0.90

    @staticmethod
    def from_env() -> "PolicyConfig":
        review = float(os.environ.get("POLICY_REVIEW_THRESHOLD", "0.70"))
        escalate = float(os.environ.get("POLICY_ESCALATE_THRESHOLD", "0.90"))

        if not (0.0 <= review <= 1.0 and 0.0 <= escalate <= 1.0):
            raise ValueError("Policy thresholds must be in [0,1]")
        if escalate < review:
            raise ValueError("POLICY_ESCALATE_THRESHOLD must be >= POLICY_REVIEW_THRESHOLD")

        return PolicyConfig(review_threshold=review, escalate_threshold=escalate)


def map_score_to_action(score: float, cfg: PolicyConfig) -> PolicyAction:
    if score >= cfg.escalate_threshold:
        return "escalate"
    if score >= cfg.review_threshold:
        return "review"
    return "allow"
