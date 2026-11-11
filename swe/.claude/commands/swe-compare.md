---
description: Compare the candidate versions of one board task. Runs the same checks in each candidate worktree, hands each diff to code-reviewer on its own, and returns a scorecard with a pick or a plain "no clear winner". Read-only; the owner picks.
argument-hint: <task-id> [base-branch]
allowed-tools: Bash, Read, Agent
model: inherit
---

Compare the candidates for task `$1` against `$2`. The base branch
defaults to `main`.

Run this from a session that built none of the candidates.

The candidates are the worktrees `.worktrees/$1-a`, `-b` and `-c` that
exist, each on its own branch from the same commit
(`scripts/task_worktree.sh add $1 <slug> --candidates 2`). With fewer
than two, say so and stop.

Steps:

1. Read the task's approved plan and acceptance criteria
   (`lattice show $1`, then the file `lattice plan $1` names). They are
   the standard. A candidate is never judged against another
   candidate's choices.
2. For each candidate capture `git -C <worktree> diff <base>...HEAD`,
   its `--stat`, and `git -C <worktree> status --short`. Uncommitted
   work is reported as not ready.
3. Run the same checks in every worktree: the checks the plan's Steps
   name, then the project's test and lint commands. Record each
   command, its exit code and the failing lines. A check that could not
   run is recorded as not run, never as passed.
4. Spawn `code-reviewer` once per candidate, at most three at once.
   Each gets one candidate's diff, the plan and the criteria, and
   nothing about the other candidates. Brief: "review this diff against
   the plan, the acceptance criteria and the SWE_CORE invariants.
   Output findings only; do not modify code."
5. Write the scorecard, one row per candidate: checks passed, failed
   and not run; criteria met, each with its evidence; reviewer findings
   by grade; lines added and removed; files changed outside the
   plan's scope.
6. Rank by the first rule that separates them: fails no check; meets
   more criteria; has no P0 or P1 finding; changes fewer files
   outside scope. If none of these separates two candidates, report
   "no clear winner" and what each does better.
7. Return the scorecard, the pick with the one rule that decided it,
   and anything a losing candidate did better that is worth carrying
   over. Offer to attach the scorecard to the task as validation
   evidence.

Do not edit, merge, link or delete anything. The owner picks, links
that one branch with `lattice branch-link`, and reviews it in the
review section like any other task.
