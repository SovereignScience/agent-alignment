---
description: Independent code review of the current branch (or a named diff). Hands off to code-reviewer; returns a verdict and material findings with file:line evidence. Read-only, no edits.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Independent code review of the current branch against `$1`. The
base branch defaults to `main`.

Capture what is under review first:

```bash
git rev-parse "${1:-main}" HEAD
git diff "${1:-main}"...HEAD --stat
git diff HEAD --stat
git ls-files --others --exclude-standard
```

That is the boundary, not the content. The reviewer reads the diff
itself, file by file; a whole diff pasted into this chat or into a brief
crowds out the lines that matter. Include committed and uncommitted
changes when they are in the requested scope, and name the untracked
source files, leaving out credentials and generated binaries. State the
base, HEAD and working-tree boundary; an empty committed diff does not
establish that prepared work is empty.

Then spawn `code-reviewer` with the base and head revisions, whether
uncommitted and untracked files are in scope, the original request, the
acceptance criteria and any validation results. Brief: "review the
change between <base> and <head> against the SWE_CORE invariants. Read
the diff yourself as your agent definition sets out, and open the code
around it as far as each question needs. Output findings and coverage
only; do not modify code. Use the format defined in your agent
definition."

Surface the verdict and findings to the user verbatim. Recommend the next
agent if findings indicate one (`security-reviewer` for trust-
boundary touches, `perf-auditor` for hot-path touches,
`regression-test-writer` for missing test coverage).

Do not commit. Do not auto-apply suggested fixes.
