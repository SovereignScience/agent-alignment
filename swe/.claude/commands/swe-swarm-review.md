---
description: Five independent SWE reviews of the current branch by code-reviewer, security-reviewer, perf-auditor, dependency-auditor, and architecture-explorer, at most three at once. Each returns a punch list; the main thread synthesizes findings without merging or rewriting.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Run a five-specialist SWE review of the current branch against
`$1`. The base branch defaults to `main`.

Capture the diff:

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

Each agent receives the same brief: "Review the diff between $1
and HEAD. Output findings only; do not modify code. Stay under
your agent's word cap."

After all five return, synthesize:

- Deduplicated severity-sorted findings.
- Conflicts between agents (one says fix X, another says X is fine).
- Items deliberately not reviewed (handoff gaps).
- Final recommendation: SHIP / SHIP-WITH-NOTE / BLOCK.

Do not merge, fix, or rewrite. Hand the synthesis back to the user.
