---
status: proposed
date: 2026-11-11
applies-to:
  - swe/.claude/agents/*.md
  - swe/.claude/commands/*.md
  - swe/SKEPTIC_ARBITER.md
  - swe/LATTICE_ONBOARDING.md
  - swe/user/CLAUDE.md
---

# ADR-0002: Grade review findings P0 to P3, and let a rule decide what holds a merge

## Context

Review findings were graded three ways at once. The code reviewer used
BLOCKER, MAJOR, MINOR and NIT. The security, dependency and performance
agents used CRITICAL to LOW. To shorten review threads, the code
reviewer was then cut to two grades, blocking or optional, while the
other agents kept theirs, so one tree gave a session two instructions.

Two grades also had the reviewer choose the merge outcome directly. The
reviewer is usually a model from the same family as the author, and
"optional" became the place for anything uncomfortable.

## Decision

A finding is graded P0 to P3 by the harm it describes, from one
definition in `swe/.claude/agents/code-reviewer.md`. Every other
reviewer file points to that definition.

The grade does not decide the merge. A written rule does: P0 and P1
hold a merge, P2 holds it only when the project is locking down and the
finding is on a path a user reaches, and P3 never does. A P0 or P1 says
what confirmed it. A suspicion that could not be confirmed is listed
apart and holds nothing.

## Rejected options

- Two grades, blocking or optional. Tried for a day. It lost the
  difference between "fix before release" and "taste", and it made the
  reviewer the judge of its own gate.
- A scale per agent. Three vocabularies meant a finding could not be
  compared across the security, dependency and code reviews, and the
  commands had no answer for a middle grade.
- A confidence number on each finding. A number cannot be checked. What
  confirmed the finding can, so each finding carries that.
- More reviewers of the same kind. In published tests two like
  reviewers did no better than one, so depth comes from a skeptic that
  must cite the code and from a second tool.

## Consequences

- Findings from every review agent, from Codex review and from
  Plannotator use the same letters and can be sorted together.
- The gate can change with the project's stage without touching any
  reviewer file.
- The definition lives in one file. A second definition, or an older
  word for a grade, is a defect.

## Confirmation

`swe/scripts/test_review_vocabulary.py` fails when a reviewer file uses
an older scale or when the grades are defined in more than one place.
