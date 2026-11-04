---
description: Run the prompt-under-test against the six standard evaluation cases plus any custom scenarios in eval/scenarios/. Hands off to scenario-evaluator. Returns a per-case PASS/FAIL/REGRESS/NEUTRAL table plus a ship/block recommendation.
argument-hint: "[path-to-prompt-under-test]"
allowed-tools: Read, Glob, Agent
model: inherit
---

Evaluate the current prompt stack (or a specific file) against scenario cases.

Input: `$1` is the file under test (default `COMPOSED_AGENT.md`).

Steps:

1. Read `eval/scenarios/*.md` to enumerate any project-specific cases.
2. Spawn `scenario-evaluator` with `$1` and the case list. Brief:
   "score each case PASS / FAIL / REGRESS / NEUTRAL with evidence and
   a one-sentence fix direction for any non-PASS. Final verdict:
   SHIP / SHIP-WITH-NOTE / BLOCK."
3. Surface the table + verdict to the user.

If the verdict is BLOCK, name which canonical-module steward should
own the fix (`inner-commons-steward`, `flourishing-auditor`,
`skeptic` author-of-record, or `repair-coach`).
