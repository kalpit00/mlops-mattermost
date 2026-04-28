# Rollback baseline (pre–large infra refactor)

Use this **full Git object name** to return the working tree to the last committed state **before** the comprehensive infrastructure and `k8s/` layout work that followed.

```text
eca5a5244ae4d800082146f5bc1c5a22fed258a5
```

- **One-line (short):** `eca5a5244a`
- **Message at that commit:** `fix(docker): copy full webapp before npm ci (postinstall needs workspaces)`

**Restore that snapshot (destructive: discards uncommitted and later commits in your working copy):**

```bash
git reset --hard eca5a5244ae4d800082146f5bc1c5a22fed258a5
```

**View only (detached `HEAD`, no branch change):**

```bash
git switch --detach eca5a5244ae4d800082146f5bc1c5a22fed258a5
```

**New branch at that point (keep current branch intact):**

```bash
git branch backup/pre-infra-eca5a52 eca5a5244ae4d800082146f5bc1c5a22fed258a5
```

> Note: If you have already **committed** newer work, use `git log` to pick the last good commit, or the branch `backup/pre-infra-eca5a52` if you create it here.

Record an updated baseline at the end of a milestone by replacing this file or adding a new dated section with `git rev-parse HEAD`.

---

## Commits *after* the baseline (e.g. `k8s/` restructure)

The baseline SHA above is the **parent** of the infrastructure rewrite. The rewrite itself may be amended or rebased, so the tip hash is not pinned here. List commits on top of the baseline with:

```bash
git log --oneline eca5a5244ae4d800082146f5bc1c5a22fed258a5..HEAD
```

**Current tip of your branch:** `git rev-parse HEAD`
