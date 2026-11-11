---
status: proposed
date: 2026-11-11
applies-to:
  - docs/ADR-*.md
  - swe/ADR_TEMPLATE.md
  - swe/scripts/adr.py
review-by: 2027-05-11
---

# ADR-0003: Keep decisions as Markdown files with front matter, found by an index and one lookup script

## Context

The repository had one decision record and a template that was used
only when the owner named a record to write. Nothing read the records.
Decisions made while planning a task stayed in the task's plan on the
private board, where a later session working in the code never looks.
Within one week a decision about how to grade review findings was made,
reversed and remade, and the reasons sat in two closed tasks.

Published work points the same way. An agent follows a decision it can
see in the code and often breaks one it cannot: in one benchmark the
baseline kept every decision visible in the codebase and between none
and a third of those recorded elsewhere. A second study found that
showing an agent a ledger of earlier commitments cut unintended design
changes several times over. A third found that models can detect a
change that violates a code-level record, which makes review the place
to check.

- Dillon and Varanasi, a vendor's benchmark of decision compliance:
  https://arxiv.org/abs/2605.08112
- "Do Coding Agents Keep Their Word?", NeurIPS 2026:
  https://neurips.cc/virtual/2026/173024
- Su and others, "Evaluating Large Language Models for Detecting
  Architectural Decision Violations": https://arxiv.org/abs/2602.07609

## Decision

A decision record is a Markdown file in `docs/`, named
`ADR-NNNN-<slug>.md`, in the shape of `swe/ADR_TEMPLATE.md`. Front
matter holds the facts tools read: status, date, who decided, what it
supersedes, which files it governs and when to look again. The prose
holds the reasoning, with the rejected options as a section of their
own.

`swe/scripts/adr.py` is the only tool. It lists the records that govern
a file, builds `docs/ADR-INDEX.md`, and checks the records and the
index. A session reads the records that apply before it plans. A
reviewer reads the records in force at the base revision. A session may
draft a record as proposed; only the owner accepts one.

## Rejected options

- A graph store with typed links and a query language. With three
  records the links fit in front matter, and a store would be the first
  dependency in a kit that runs on the standard library.
- Path-scoped rule files in `.claude/rules/`. They load only in Claude
  Code, are reported not to load in subagents, and Codex would see
  nothing.
- Leaving decisions in board plans. A plan is private, belongs to one
  task and is closed with it.
- A summary of every decision in the always-loaded guides. Those files
  are within a few bytes of the size Codex reads, and most decisions do
  not bear on most tasks.
- A full YAML parser. Only `key: value` and simple lists are read, and
  anything else is an error, so a record cannot mean different things to
  different readers.

## Consequences

- A decision costs one short file and one index line, and it outlives
  the task that made it.
- A change that goes against an accepted record must say so, by
  proposing the record that replaces it.
- The index is generated. A record edited without rebuilding it fails
  the check.
- This is worth a second look once there are dozens of records or
  several repositories share them, which is when a graph starts to pay.

## Confirmation

`python3 swe/scripts/adr.py check` passes, and
`swe/scripts/test_adr.py` runs it on this repository.
