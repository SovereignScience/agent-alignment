---
status: proposed
date: YYYY-MM-DD
applies-to:
  - path/or/glob/the/decision/governs
---

# ADR-NNNN: The decision, as a short statement

Copy this file to `docs/ADR-NNNN-<slug>.md`, with the next free number.
Write a record for a choice that is hard to undo, or that rejects an
option someone will reach for again. A choice that is cheap to reverse
needs none. One record holds one decision, in one or two screens, and
stands alone: a reader who never saw the task can follow it.

The front matter holds the facts tools read. `status` is `proposed`,
`accepted`, `rejected` or `superseded`. A record drafted by a session
starts as `proposed`; only the owner changes it to `accepted`, and adds
`decision-makers` then. `applies-to` lists the files the decision
governs, as globs from the repository root. Add `supersedes: ADR-NNNN`
when this record replaces another, and `review-by: YYYY-MM-DD` when the
decision rests on something that may change.

An accepted record's decision is not edited. To change course, write a
new record that supersedes it, and set the old one's status to
`superseded` when the new one is accepted. After any change run
`python3 swe/scripts/adr.py index --write` and `adr.py check`.

## Context

What forced a choice: the problem, the constraints, what was true at the
time. Facts, with their sources.

## Decision

What was chosen, stated so that a change can be checked against it.

## Rejected options

Each option that was considered and not taken, and why. This is the part
a later reader needs most: it stops the same idea being tried again
without the reason it failed.

## Consequences

What follows, good and bad: what becomes easier, what becomes harder,
what must now be kept true.

## Confirmation

How anyone can tell the decision is still being followed: a test, a
check, or what a reviewer looks for.
