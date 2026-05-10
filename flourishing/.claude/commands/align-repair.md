---
description: Given a transcript with a rupture signal (or a self-detected error), draft the repair-sequence response. Hands off to repair-coach. Returns severity classification + the rewritten reply + any longitudinal constraint to persist.
argument-hint: <path-to-transcript-or-quoted-text>
allowed-tools: Read, Agent
model: inherit
---

Draft a repair-sequence response from a transcript or a self-detected
error description.

Input: `$ARGUMENTS` is either a path to a transcript file or the
transcript inline in triple backticks. Include the user's last turn(s)
plus the agent draft that triggered the rupture (if applicable).

Steps:

1. Spawn `repair-coach` with the transcript. Brief: "classify severity
   (Minor / Moderate / Major), produce the repair-sequence response in
   the agent's natural voice, and surface any longitudinal constraint
   the user imposed."
2. Output: severity, the rewritten response, longitudinal constraint
   (or `none`).

Do not edit `REPAIR_PROTOCOL.md` from this command — that is module-
authoring, not coaching. Use `repair-coach` in author-mode for that.
