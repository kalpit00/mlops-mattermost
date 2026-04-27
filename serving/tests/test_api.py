from __future__ import annotations

from fastapi.testclient import TestClient

from serving.app.main import app, loader


class DummyPipeline:
    def predict_proba(self, texts):  # noqa: ANN001
        # [p(non-toxic), p(toxic)]
        return [[0.2, 0.8] for _ in texts]


def test_health() -> None:
    # Prime test loader.
    loader._pipeline = DummyPipeline()  # type: ignore[attr-defined]
    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["model_loaded"] is True


def test_score_success() -> None:
    loader._pipeline = DummyPipeline()  # type: ignore[attr-defined]
    client = TestClient(app)

    r = client.post(
        "/score",
        json={"text": "You are useless", "channel_type": "public", "prior_violation_count": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert 0.0 <= data["toxicity_score"] <= 1.0
    assert "model_version" in data
    assert data["policy_action"] in {"allow", "review", "escalate"}


def test_score_model_not_loaded() -> None:
    loader._pipeline = None  # type: ignore[attr-defined]
    client = TestClient(app)

    r = client.post("/score", json={"text": "test"})
    assert r.status_code == 503
