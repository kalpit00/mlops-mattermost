from __future__ import annotations

from ray import serve
from starlette.requests import Request

from serving.app.model_loader import ModelConfig, ModelLoader
from serving.app.policy import PolicyConfig, map_score_to_action
from serving.app.schemas import ScoreRequest, ScoreResponse


@serve.deployment(num_replicas=1, ray_actor_options={"num_cpus": 1})
class ToxicityModel:
    def __init__(self) -> None:
        self.model_cfg = ModelConfig.from_env()
        self.policy_cfg = PolicyConfig.from_env()
        self.loader = ModelLoader(self.model_cfg)
        self.loader.load()

    async def __call__(self, request: Request) -> ScoreResponse:
        body = await request.json()
        req = ScoreRequest.model_validate(body)
        score = self.loader.score(req.text)
        action = map_score_to_action(score, self.policy_cfg)
        return ScoreResponse(
            toxicity_score=score,
            model_version=self.loader.model_version,
            policy_action=action,
            degraded=False,
        )


toxicity_app = ToxicityModel.bind()
