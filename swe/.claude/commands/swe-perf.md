---
description: Performance audit of a hot path or a diff. Hands off to perf-auditor; returns a numbered list of issues with measurement and fix direction. Read-only, no edits.
argument-hint: <path-or-diff-description>
allowed-tools: Bash, Read, Agent
model: inherit
---

Audit a code path or a diff for performance issues against the
project's perf budgets.

Input: `$ARGUMENTS` is the path, the file, or a description of the
hot path under audit. If empty, ask for the workload shape.

Steps:

1. Spawn `perf-auditor`. Brief: "audit per the format defined in
   your agent definition. Cite the budget. Cite measurement when
   you have it; name the measurement to take when you don't. Cap
   at 500 words."
2. Surface the punch list to the user verbatim.
3. If findings reveal a missing CI gate for a load-bearing budget,
   recommend adding one.

Do not implement the optimization from this command.
