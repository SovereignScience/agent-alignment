---
description: Full bug-fix loop — debugger diagnoses, regression-test-writer locks the test, the user implements the fix, code-reviewer verifies. Returns root-cause diagnosis + failing test before any production code is changed.
argument-hint: <bug-description-or-failure-output>
allowed-tools: Bash, Read, Edit, Write, Agent
model: inherit
---

Coordinate a disciplined bug-fix loop.

Input: `$ARGUMENTS` is the bug report, the failing test output, or
the user's description. If empty, ask for the failing observation.

Steps:

1. Spawn `debugger` with the bug report. Brief: "diagnose to root
   cause with file:line evidence. Output the format defined in your
   agent definition. Confidence HIGH/MEDIUM/LOW. Do not propose a
   fix."
2. After diagnosis returns, spawn `regression-test-writer` with the
   diagnosis. Brief: "write a failing test that reproduces the
   diagnosed bug. Confirm it fails on the current code. Use the
   project's existing fixtures."
3. Surface the diagnosis + the failing test to the user. Recommend
   they (or a named specialist) implement the fix.
4. After the user reports the fix is in, spawn `code-reviewer` on
   the resulting diff to confirm no symptom-patching, no scope
   creep, and that the new test now passes.

Do not implement the production fix from this command — diagnose,
test, review only.
