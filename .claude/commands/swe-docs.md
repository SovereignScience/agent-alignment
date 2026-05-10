---
description: Write or update documentation that earns its keep — README sections, ADRs, runbooks, CHANGELOG entries. Hands off to docs-writer; refuses to add docs that just restate code.
argument-hint: <doc-type-and-target>
allowed-tools: Bash, Read, Edit, Write, Agent
model: inherit
---

Write or update documentation for the named target.

Input: `$ARGUMENTS` is what to document — e.g. "ADR for the choice
to use postgres over sqlite", "README quickstart for the CLI", "a
runbook for restarting the worker fleet".

Steps:

1. Spawn `docs-writer`. Brief: "write the named doc per the format
   defined in your agent definition. Default to bullets and tables.
   Refuse to add docs that just restate code. For ADRs, use the
   four-part Context/Decision/Consequences/Alternatives shape."
2. Surface the diff (or new file) to the user.
3. If a CHANGELOG.md exists, recommend adding the user-facing
   summary there too.
