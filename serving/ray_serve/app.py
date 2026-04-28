from __future__ import annotations

import time

from ray import serve
from starlette.requests import Request

from serving.app.logging_utils import log_inference_event
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
        start = time.perf_counter()
        text_length = None
        scenario = request.headers.get("X-Load-Scenario")
        try:
            body = await request.json()
            req = ScoreRequest.model_validate(body)
            text_length = len(req.text)
            score = self.loader.score(req.text)
            action = map_score_to_action(score, self.policy_cfg)
            log_inference_event(
                runtime="ray",
                endpoint="/",
                status_code=200,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                model_version=self.loader.model_version,
                policy_action=action,
                degraded=False,
                text_length=text_length,
                scenario=scenario,
            )
            return ScoreResponse(
                toxicity_score=score,
                model_version=self.loader.model_version,
                policy_action=action,
                degraded=False,
            )
        except Exception as exc:
            log_inference_event(
                runtime="ray",
                endpoint="/",
                status_code=500,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                model_version=self.loader.model_version,
                degraded=True,
                text_length=text_length,
                scenario=scenario,
                error=type(exc).__name__,
            )
            raise


toxicity_app = ToxicityModel.bind()
