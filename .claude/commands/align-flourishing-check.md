---
description: Audit a planned request, feature, or response for material third-party / civic / labor / ecological externalities. Hands off to flourishing-auditor in auditor mode. Returns who is in/out of the room, what is shifted off-screen, and a surface verdict.
argument-hint: <request-description>
allowed-tools: Read, Agent
model: inherit
---

Run a Flourishing-Protocol audit against a request or feature.

Input: `$ARGUMENTS` is the request or feature in plain language. If
empty, ask the user to paste the request.

Steps:

1. Spawn `flourishing-auditor` in auditor mode. Brief: "run the audit
   format defined in your agent definition. Be material, not
   speculative. Cap at 250 words. Verdict: STAY INVISIBLE / FLAG
   MATERIALLY / REDIRECT / DECLINE."
2. Surface the audit to the user verbatim.

Do not refuse the request from this command — the auditor's verdict
informs the calling agent's next move; the human decides.
