## Swift replication (Chameleon `Objstore_proj17`)

This repo normally writes to an S3-compatible object store (MinIO). This adds **optional** replication to **OpenStack Swift** (Chameleon).

### 1) Mattermost server uploads (MinIO -> Swift)

When enabled, every successful S3 `PutObject` through Mattermost’s filestore will enqueue an async copy into Swift.

- **Source**: your existing MinIO bucket/key (whatever Mattermost writes)
- **Destination Swift object name**: `mattermost/<bucket>/<key>`

Enable with environment variables (set wherever you run the Mattermost server):

- `MM_SWIFT_REPLICATION_ENABLED=1`
- `MM_SWIFT_CLOUDS_YAML_PATH=clouds.yaml` (default: `clouds.yaml` in the working directory)
- `MM_SWIFT_CLOUD=openstack` (default: `openstack`)
- `MM_SWIFT_CONTAINER=Objstore_proj17` (required)
- `MM_SWIFT_PREFIX=mattermost` (default: `mattermost`)

Notes:
- This is **best-effort** (non-blocking). If Swift is down, your app still works and MinIO remains the source of truth.
- Don’t commit `clouds.yaml` to git.

### 2) MLOps artifacts (pipelines -> MinIO + Swift)

The Python pipelines can optionally upload the same generated artifacts to Swift (in addition to MinIO) using `openstacksdk`.

Enable with:

- `MLOPS_SWIFT_ENABLED=1`
- `MLOPS_SWIFT_CLOUDS_YAML_PATH=clouds.yaml` (default: `clouds.yaml`)
- `MLOPS_SWIFT_CLOUD=openstack` (default: `openstack`)
- `MLOPS_SWIFT_CONTAINER=Objstore_proj17` (required)
- `MLOPS_SWIFT_PREFIX=moderation-data` (default: `moderation-data`)

Uploaded object names mirror the MinIO keys, under the prefix, e.g.:
- `moderation-data/raw/jigsaw/train.csv`
- `moderation-data/transformed/jigsaw/comments_binary.parquet`
- `moderation-data/nightly/<date>/labeled_messages.parquet`
- `moderation-data/datasets/<date>/train.parquet`

### 3) Kubernetes: ML moderation logs sidecar (PVC -> Swift)

The Mattermost Deployment can run an additional sidecar (`mlmoderation-swift-uploader`) that:

- Creates Swift “folder” markers under **one container** (for example `Objstore_proj17`) at:
  - `moderation-data/raw/jigsaw/.keep`
  - `moderation-data/transformed/jigsaw/.keep`
  - `moderation-data/nightly/.keep`
  - `moderation-data/online_features/.keep`
  - `moderation-data/datasets/.keep`
  - `moderation-data/mlmoderation/.keep`
- Mirrors files from `/mattermost/data/mlmoderation/**` into Swift as:
  - `moderation-data/mlmoderation/<relative-path>`

This is intentionally separate from Mattermost attachment replication (section 1), which uses the `mattermost/` prefix by default.

Apply the ConfigMap once, then apply/update the Deployment:

```bash
kubectl apply -f infrastructure/k8s/mattermost/mlmoderation-swift-sidecar-configmap.yaml
kubectl apply -f infrastructure/k8s/mattermost/mattermost-deployment.yaml
```

### Quick smoke check

1. Put `clouds.yaml` at the repo root (or set the `*_CLOUDS_YAML_PATH` variable).
2. Enable the relevant flags above.
3. Upload a file attachment in Mattermost.
4. In Chameleon Swift (`Objstore_proj17`), look for an object under `mattermost/...`.
5. Run one pipeline (e.g. synthetic) and look for objects under `moderation-data/...`.
6. If you enabled the Kubernetes Swift sidecar, confirm the marker objects exist under `moderation-data/...` and JSONL files appear under `moderation-data/mlmoderation/...`.

