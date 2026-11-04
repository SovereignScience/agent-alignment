---
description: Five-way independent review of the current branch by inner-commons-steward, flourishing-auditor, repair-coach, drift-checker, and pr-rubric-reviewer at most three at once. Each returns a punch list; the main thread synthesizes findings without merging or rewriting.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Run a parallel five-specialist review of the current branch against
`$1` (default `main`).

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


Then dispatch the five requested reviewers, at most three at once:

1. `inner-commons-steward`: semantics check on Inner Commons changes.
2. `flourishing-auditor`: module-author mode if FLOURISHING_PROTOCOL
   touched; auditor mode if a behavioral change has externality
   implications.
3. `repair-coach`: author-mode review if REPAIR_PROTOCOL touched.
4. `drift-checker`: canonical-vs-derived consistency.
5. `pr-rubric-reviewer`: five-questions + six-rubric-checks.

Each agent receives the same brief: "Review the diff between `$1`
and HEAD. Output findings only. Do not modify code. Stay under your
agent's word cap."

After all five return, synthesize:

- A deduplicated severity-sorted finding list.
- Conflicts between agents (where one says fix-X and another says X is
  fine).
- Items deliberately not reviewed (handoff gaps).
- Final recommendation: SHIP / SHIP-WITH-NOTE / BLOCK.

Do not merge, fix, or rewrite. Hand the synthesis back to the user.
