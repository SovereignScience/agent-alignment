---
description: Audit dependency changes (adds, removes, version bumps, lockfile drift) for CVEs, license drift, maintenance signal, and bundle bloat. Hands off to dependency-auditor; read-only — no edits.
argument-hint: [base-branch]
allowed-tools: Bash, Read, Agent
model: inherit
---

Audit dependency changes against `$1` (default `main`).

Capture the manifest and lockfile diffs:

```bash
git diff "${1:-main}"...HEAD -- package.json package-lock.json yarn.lock pnpm-lock.yaml
git diff "${1:-main}"...HEAD -- pyproject.toml requirements.txt poetry.lock uv.lock
git diff "${1:-main}"...HEAD -- Cargo.toml Cargo.lock go.mod go.sum
```

Then spawn `dependency-auditor`. Brief: "audit per the format
defined in your agent definition. For ADD and BUMP-MAJOR, check
CVEs and maintenance signal. For REMOVE, grep for remaining
imports. Confirm lockfile and manifest agree. Cap at 400 words."

Surface the verdict to the user. If CRITICAL or HIGH findings,
recommend BLOCK-MERGE.

Do not modify any manifest or lockfile.
