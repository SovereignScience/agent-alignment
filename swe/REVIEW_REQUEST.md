# Review request

Fill this in when you hand a change to an independent reviewer, a person or
a fresh agent that has not seen your session. Give evidence, not your
verdict: a reviewer handed your conclusion tends to confirm it.

```
Review request (read-only)

Repo: <absolute path>
Range: <base>..<head> (branch <name>)
Goal: <what the change must do, or the path to its spec>
What changed and why: <two to four lines, by file or component>
Known risks and trade-offs: <what could break, downsides accepted>
Checks run (claims to verify):
- <command> -> <exit status, key output or log path>
Never ran: <tests, environments or live paths not exercised, and why>
Focus on: <invariants, edge cases, failure paths>
Skip: style, naming, anything CI or lint enforces, <paths>
Limits: read-only. No edits, commits, pushes or host contact.

Report back:
- Blocking: file:line, what breaks, the code or output that shows it,
  and how you confirmed it
- Optional: at most five, one line each
- Pre-existing, not from this change: listed separately
- What you checked and what you did not
- Verdict: blocking findings yes or no, not a guarantee
```
