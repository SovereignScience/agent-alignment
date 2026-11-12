---
description: Independent security review of the current branch (or a named diff). Hands off to security-reviewer; returns findings graded P0 to P3 against the OWASP top-10. Read-only, no edits.
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

Surface the findings to the user verbatim. If there is a P0 or P1
finding, recommend BLOCK-MERGE. If the worst is P2, recommend
SHIP-WITH-NOTE, or BLOCK-MERGE when the board is in lock down and the
finding is on a path a user reaches. If only P3, recommend SHIP.

Do not commit. Do not auto-apply fixes.
