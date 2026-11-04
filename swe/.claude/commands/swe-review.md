---
description: Independent code review of the current branch (or a named diff). Hands off to code-reviewer; returns a verdict and material findings with file:line evidence. Read-only, no edits.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Independent code review of the current branch against `$1`. The
base branch defaults to `main`.

Capture the diff first:

```bash
git diff "${1:-main}"...HEAD --stat
git diff "${1:-main}"...HEAD
git diff HEAD --stat
git diff HEAD
git ls-files --others --exclude-standard
```

Include committed and uncommitted changes when they are in the requested
scope. Read the listed untracked source files without opening credentials
or generated binaries. State the base, HEAD and working-tree boundary;
an empty committed diff does not establish that prepared work is empty.

Then spawn `code-reviewer` with the diff, the original request and
any validation results. Brief: "review the diff between $1 and HEAD
against the SWE_CORE invariants. Output findings only; do not modify
code. Use the format defined in your agent definition."

Surface the verdict and findings to the user verbatim. Recommend the next
agent if findings indicate one (`security-reviewer` for trust-
boundary touches, `perf-auditor` for hot-path touches,
`regression-test-writer` for missing test coverage).

Do not commit. Do not auto-apply suggested fixes.
