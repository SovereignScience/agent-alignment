---
description: Five independent SWE reviews of the current branch by code-reviewer, security-reviewer, perf-auditor, dependency-auditor, and architecture-explorer, at most three at once. Each returns a punch list; the main thread synthesizes findings without merging or rewriting.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Run a five-specialist SWE review of the current branch against
`$1`. The base branch defaults to `main`.

Capture what is under review:

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

Then dispatch the five agents, at most three at once:

1. `code-reviewer`: root-cause, dead code, source-of-truth,
   tests-cover-the-branch.
2. `security-reviewer`: OWASP top-10 across every trust-boundary
   touch.
3. `perf-auditor`: only if hot paths or render loops are touched;
   otherwise the agent should report "no hot path in scope, audit
   skipped" and return.
4. `dependency-auditor`: only if a manifest or lockfile changed;
   otherwise return "no dep changes, audit skipped".
5. `architecture-explorer`: read the diff plus the surrounding
   directory and confirm the change fits the existing architecture
   (no surprise abstractions, no surprise dependencies between
   layers).

Each agent receives the same brief, with the base and head revisions,
the original request, the acceptance criteria and any validation
results: "Review the change between <base> and <head>. Read the diff
yourself and open the code around it as far as each question needs.
Output findings and what you read; do not modify code. Keep the prose
short and never drop a finding to fit a length."

After all five return, synthesize:

- Deduplicated findings, highest grade first.
- Conflicts between agents (one says fix X, another says X is fine).
- Items deliberately not reviewed (handoff gaps).
- Final recommendation: SHIP / SHIP-WITH-NOTE / BLOCK.

Do not merge, fix, or rewrite. Hand the synthesis back to the user.
