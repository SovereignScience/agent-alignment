---
description: Independent code review of the current branch (or a named diff). Hands off to code-reviewer; returns a severity-sorted findings list with file:line evidence and concrete fix directions. Read-only — no edits.
argument-hint: [base-branch]
allowed-tools: Bash, Read, Agent
model: inherit
---

Independent code review of the current branch against `$1`
(default `main`).

Capture the diff first:

```bash
git diff "${1:-main}"...HEAD --stat
git diff "${1:-main}"...HEAD
```

Then spawn `code-reviewer` with the diff. Brief: "review the diff
between $1 and HEAD against the SWE_CORE invariants. Output
findings only — do not modify code. Use the format defined in your
agent definition. Cap at 500 words."

Surface the punch list to the user verbatim. Recommend the next
agent if findings indicate one (`security-reviewer` for trust-
boundary touches, `perf-auditor` for hot-path touches,
`regression-test-writer` for missing test coverage).

Do not commit. Do not auto-apply suggested fixes.
