---
description: Diagnose a failing test, exception, or unexpected behavior to root cause. Hands off to debugger; returns mechanism + evidence + reproducer + recommended fix direction. Does not apply the fix.
argument-hint: <failure-description-or-stack-trace>
allowed-tools: Bash, Read, Agent
model: inherit
---

Diagnose a failing observation to root cause.

Input: `$ARGUMENTS` is the failure — a stack trace, a failing test
output, a "this returns wrong values" report. If empty, ask for the
failing observation.

Steps:

1. Spawn `debugger`. Brief: "diagnose per the format defined in
   your agent definition. Cite file:line for every claim. Trigger
   vs. root cause separately. Confidence HIGH/MEDIUM/LOW. Cap at
   400 words."
2. Surface the diagnosis to the user.
3. Recommend handoff:
   - `regression-test-writer` to lock the bug as a test
   - The user (or a named implementer) for the fix
   - `code-reviewer` after the fix to confirm no symptom-patching
