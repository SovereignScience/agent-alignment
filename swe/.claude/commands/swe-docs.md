---
description: "Update documentation in place: README sections, runbooks, API references. Creates an ADR or a CHANGELOG entry only when the user names the file. Hands off to docs-writer; refuses to add docs that just restate code."
argument-hint: <doc-type-and-target>
allowed-tools: Bash, Read, Edit, Write, Agent
model: inherit
---

Update documentation for the named target.

Input: `$ARGUMENTS` is what to document, e.g. "README quickstart
for the CLI", "a runbook for restarting the worker fleet", or, when
the user names the file, "ADR-0007 for the choice to use postgres
over sqlite".

Steps:

1. Spawn `docs-writer`. Brief: "edit the existing doc in place per
   the format defined in your agent definition. Create a new file
   only if the user named it in this turn. Default to bullets and
   tables. Refuse to add docs that just restate code. For a named
   ADR, use the four-part Context/Decision/Consequences/Alternatives
   shape."
2. Surface the diff to the user.
3. Add a CHANGELOG entry only if the user named `CHANGELOG.md`.
