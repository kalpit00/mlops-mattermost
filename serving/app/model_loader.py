from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from typing import Any

import joblib


@dataclass(frozen=True)
class ModelConfig:
    model_path: str
    model_version: str

    @staticmethod
    def from_env() -> "ModelConfig":
        raw = os.environ.get("MODEL_PATH", "").strip()
        # Ignore copy-paste tutorial placeholders so default /models/... is used.
        if raw in ("/path/to/tfidf_logreg_pipeline.joblib", "/path/to/pipeline.joblib"):
            raw = ""
        model_path = raw or "/models/tfidf_logreg_pipeline.joblib"
        return ModelConfig(
            model_path=model_path,
            model_version=os.environ.get("SERVING_MODEL_VERSION", "tfidf-logreg").strip() or "tfidf-logreg",
        )


class ModelLoader:
    def __init__(self, config: ModelConfig):
        self._config = config
        self._pipeline: Any | None = None
        self._lock = Lock()

    @property
    def model_version(self) -> str:
        return self._config.model_version

    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load(self) -> None:
        if not os.path.exists(self._config.model_path):
            raise FileNotFoundError(
                f"MODEL_PATH does not exist: {self._config.model_path!r}. "
                "Unset MODEL_PATH to use the default /models/tfidf_logreg_pipeline.joblib (Kubernetes), "
                "or set MODEL_PATH to a real file, e.g. after: "
                "kubectl -n mlops-serving cp <pod>:/models/tfidf_logreg_pipeline.joblib ./.cache/"
            )

        with self._lock:
            self._pipeline = joblib.load(self._config.model_path)

    def score(self, text: str) -> float:
        if self._pipeline is None:
            raise RuntimeError("model not loaded")

        proba = self._pipeline.predict_proba([text])
        if proba.shape[1] < 2:
            raise RuntimeError("unexpected model output shape")

        toxic_p = float(proba[0, 1])
        if toxic_p < 0.0 or toxic_p > 1.0:
            raise RuntimeError("model returned invalid probability")
        return toxic_p
