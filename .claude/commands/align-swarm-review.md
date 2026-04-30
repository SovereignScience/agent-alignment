---
description: Five-way independent review of the current branch by inner-commons-steward, flourishing-auditor, repair-coach, drift-checker, and pr-rubric-reviewer in parallel. Each returns a punch list; the main thread synthesizes findings without merging or rewriting.
argument-hint: [base-branch]
allowed-tools: Bash, Read, Agent
model: inherit
---

Run a parallel five-specialist review of the current branch against
`$1` (default `main`).

Capture the diff first:

```bash
git diff "$1"...HEAD --stat
git diff "$1"...HEAD
```

Then dispatch all five agents **in parallel** in a single message:

1. `inner-commons-steward` — semantics check on Inner Commons changes.
2. `flourishing-auditor` — module-author mode if FLOURISHING_PROTOCOL
   touched; auditor mode if a behavioral change has externality
   implications.
3. `repair-coach` — author-mode review if REPAIR_PROTOCOL touched.
4. `drift-checker` — canonical-vs-derived consistency.
5. `pr-rubric-reviewer` — five-questions + six-rubric-checks.

Each agent receives the same brief: "Review the diff between `$1`
and HEAD. Output findings only — do not modify code. Stay under your
agent's word cap."

After all five return, synthesize:

- A deduplicated severity-sorted finding list.
- Conflicts between agents (where one says fix-X and another says X is
  fine).
- Items deliberately not reviewed (handoff gaps).
- Final recommendation: SHIP / SHIP-WITH-NOTE / BLOCK.

Do not merge, fix, or rewrite. Hand the synthesis back to the user.
