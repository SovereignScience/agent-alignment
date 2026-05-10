---
description: Plan a behavior-preserving refactor before any code changes. Hands off to refactoring-planner; returns a stepwise atomic plan with a test backstop and a rollback point. Does not perform the refactor.
argument-hint: <scope-or-target>
allowed-tools: Bash, Read, Agent
model: inherit
---

Plan a refactor of the named scope.

Input: `$ARGUMENTS` is the file, the directory, or the description
of what should be refactored. If empty, ask for the scope and the
target shape.

Steps:

1. Spawn `refactoring-planner` with the scope. Brief: "produce the
   stepwise plan defined in your agent definition. Each step
   atomic, each step revertable, each step gated by tests passing.
   Cap at 500 words."
2. Surface the plan to the user.
3. If the plan starts with characterization tests (Step 0), offer
   to spawn `regression-test-writer` to write them before any
   restructure begins.
4. Do not perform any step. The user (or a named implementer)
   executes the plan one step at a time, with `code-reviewer`
   between steps if the steps are large.
