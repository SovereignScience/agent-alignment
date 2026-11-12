---
description: Independent security review of the current branch (or a named diff). Hands off to security-reviewer; returns severity-sorted CRITICAL/HIGH/MEDIUM/LOW findings against the OWASP top-10. Read-only, no edits.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Independent security review of the current branch against `$1`.
The base branch defaults to `main`.

Capture what is under review first:

```bash
git rev-parse "${1:-main}" HEAD
git diff "${1:-main}"...HEAD --stat
```

Then spawn `security-reviewer` with the base and head revisions. Brief:
"review the change between <base> and <head> per the format defined in
your agent definition. Read the diff yourself, and follow each input
into the unchanged code that supplies or consumes it. Walk the OWASP
top-10 quick-check on every hunk that touches a trust boundary. Output
findings only; do not modify code. Keep the prose under 500 words and
never drop a finding to fit."

Surface the findings to the user verbatim. If there are CRITICAL or
HIGH findings, recommend BLOCK-MERGE. If only LOW/INFO, recommend
SHIP-WITH-NOTE.

Do not commit. Do not auto-apply fixes.
