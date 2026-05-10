---
description: Independent security review of the current branch (or a named diff). Hands off to security-reviewer; returns severity-sorted CRITICAL/HIGH/MEDIUM/LOW findings against the OWASP top-10. Read-only — no edits.
argument-hint: [base-branch]
allowed-tools: Bash, Read, Agent
model: inherit
---

Independent security review of the current branch against `$1`
(default `main`).

Capture the diff first:

```bash
git diff "${1:-main}"...HEAD --stat
git diff "${1:-main}"...HEAD
```

Then spawn `security-reviewer` with the diff. Brief: "review per
the format defined in your agent definition. Walk the OWASP top-10
quick-check on every hunk that touches a trust boundary. Output
findings only — do not modify code. Cap at 500 words."

Surface the findings to the user verbatim. If there are CRITICAL or
HIGH findings, recommend BLOCK-MERGE. If only LOW/INFO, recommend
SHIP-WITH-NOTE.

Do not commit. Do not auto-apply fixes.
