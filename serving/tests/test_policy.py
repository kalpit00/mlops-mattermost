from serving.app.policy import PolicyConfig, map_score_to_action


def test_policy_allow() -> None:
    cfg = PolicyConfig(review_threshold=0.7, escalate_threshold=0.9)
    assert map_score_to_action(0.2, cfg) == "allow"


def test_policy_review() -> None:
    cfg = PolicyConfig(review_threshold=0.7, escalate_threshold=0.9)
    assert map_score_to_action(0.75, cfg) == "review"


def test_policy_escalate() -> None:
    cfg = PolicyConfig(review_threshold=0.7, escalate_threshold=0.9)
    assert map_score_to_action(0.95, cfg) == "escalate"
