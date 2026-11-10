---
description: Check that a reported issue is real before it becomes a board task. Hands off to debugger to reproduce it; returns a verdict with evidence and, for a valid issue, a drafted task for the owner to authorize. Creates nothing on the board and edits no file.
argument-hint: <issue-report-or-observation>
allowed-tools: Bash, Read, Agent
model: inherit
---

Decide whether `$ARGUMENTS` describes a real issue, and draft the task
if it does.

Input: the report, the failing output or the user's description. If
empty, ask what was run, what happened and what was expected.

Steps:

1. Look for the same issue on the board: `lattice list`, then the
   titles and descriptions under `.lattice/tasks/` for the affected
   area. If an open task already covers it, name that task and stop.
2. Spawn `debugger` with the report. Brief: "reproduce this on the
   integration branch and diagnose to root cause with file:line
   evidence. Run only read-only commands and the project's tests; edit
   no file. If it does not reproduce, say what you ran and what you
   saw. Do not propose a fix."
3. Give one verdict, with its evidence:
   - VALID: reproduced. The command and its output.
   - NOT REPRODUCED: what was tried, and what would settle it.
   - NOT A DEFECT: the behaviour is intended. The doc or test that
     says so.
   - DUPLICATE: the task that covers it.
4. For VALID only, draft the task in the board's description shape
   (Request, Scope, Owner, Coverage boundary, Remaining) with a title,
   type and priority, and one acceptance criterion per outcome a
   reviewer can check. The reproduction is the first criterion's check.

Do not create the task, write a test into the checkout or start the
fix. The owner authorizes the task. The failing test is written later,
in the task's worktree, with `/swe-add-test`.
