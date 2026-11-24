---
description: Score real model replies to the scenarios in eval/scenarios/, from the newest result file in eval/results/ or a pasted transcript. Hands off to scenario-evaluator. Returns a per-case PASS/FAIL/REGRESS/NEUTRAL/NOT RUN table plus a ship/block recommendation.
argument-hint: "[path-to-prompt-under-test]"
allowed-tools: Read, Glob, Agent
model: inherit
---

Evaluate the current prompt stack (or a specific file) against scenario cases.

Input: `$1` is the file under test (default `COMPOSED_AGENT.md`). The
evaluation command runs `COMPOSED_AGENT.md` only; for any other file
there are no real replies unless the user pastes a transcript.

Steps:

1. Read `eval/scenarios/*.md` to enumerate the cases.
2. Look for a result file in `eval/results/`. If there is none and the
   user pasted no transcript, tell the user nothing has been run, give
   the evaluation command from `CLAUDE.md` under "Build, verify", and
   stop. The command calls a model and needs the user's API key, so
   the user runs it.
3. Spawn `scenario-evaluator` with `$1`, the case list and the result
   file or transcript. Brief: "score each case PASS / FAIL / REGRESS /
   NEUTRAL / NOT RUN from the real replies, with the quoted reply as
   evidence and a one-sentence fix direction for any FAIL or REGRESS.
   Final verdict: SHIP / SHIP-WITH-NOTE / BLOCK."
4. Surface the table + verdict to the user.

If the verdict is BLOCK, name which canonical-module steward should
own the fix (`inner-commons-steward`, `flourishing-auditor`,
`skeptic` author-of-record, or `repair-coach`).
