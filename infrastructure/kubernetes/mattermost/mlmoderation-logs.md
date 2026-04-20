## ML moderation logs → platform MinIO (data step)

Mattermost writes moderation ML JSONL logs and moderator feedback under its persistent volume:

- `/mattermost/data/mlmoderation/logs/online_features_v1.jsonl`
- `/mattermost/data/mlmoderation/logs/online_scores_v1.jsonl`
- `/mattermost/data/mlmoderation/feedback/moderation_feedback_v1.jsonl`
- `/mattermost/data/mlmoderation/feedback/moderation_feedback_v2.jsonl` (includes `text` + `user_hash`)

The `mattermost-deployment.yaml` includes a sidecar container that mirrors `/mattermost/data/mlmoderation` into **platform MinIO**:

- `s3://moderation-data/mlmoderation/...`

### Required secret (do not commit values)

Create the MinIO credentials secret **in the `mattermost` namespace** (same values as the platform MinIO root user/password):

```bash
kubectl create namespace mattermost --dry-run=client -o yaml | kubectl apply -f -

kubectl -n mattermost create secret generic minio-secret \
  --from-literal=root-user='REPLACE_ME' \
  --from-literal=root-password='REPLACE_ME' \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Verify
- Post/flag/keep/remove a message in Mattermost.
- Confirm files exist in the Mattermost pod under `/mattermost/data/mlmoderation/...`.
- Confirm objects appear in MinIO under `moderation-data/mlmoderation/...`.

