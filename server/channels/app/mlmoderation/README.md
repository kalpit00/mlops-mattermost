# `mlmoderation` — online features, scores, and feedback (Go)

Runtime hooks for the moderation ML track. Enabled via `MM_MLMODERATION_*` environment variables (see `service.go` / `log.go`).

| Concern | Output (default under `data/mlmoderation/`, gitignored) |
|--------|--------------------------------------------------------|
| Feature rows for drift / debugging | `logs/online_features_v1.jsonl` |
| Model scores | `logs/online_scores_v1.jsonl` |
| Moderator outcomes (retrain labels) | `feedback/moderation_feedback_v1.jsonl` |

**Note:** `logs/online_scores_v1.jsonl` is currently written by a **heuristic scorer** (`scoring.go`). It’s intended to be replaced by a real ML model call (input: `FeatureRowV1`, output: `ScoreRowV1`).

These JSONL paths feed **`data.pipelines.cli_dataset_build`** (feedback glob) and **`data.pipelines.cli_monitoring`** (live window). No secrets should be written into these files; use existing Mattermost config for credentials.

**Related:** [`data/README.md`](../../../../data/README.md), [`data/pipelines/README.md`](../../../../data/pipelines/README.md).
