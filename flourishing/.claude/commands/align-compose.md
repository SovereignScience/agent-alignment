---
description: Propagate a canonical-module change into COMPOSED_AGENT.md and the three provider variants (FOR_CLAUDE.md, FOR_CHATGPT.md, FOR_API.md). Hands the work to module-composer; finishes with a drift-check.
argument-hint: [canonical-file]
allowed-tools: Bash, Read, Edit, Agent
model: inherit
---

Recompose derived files from canonical modules.

If `$1` is provided, treat it as the canonical module that just
changed (one of: `INNER_COMMONS_CORE.md`, `FLOURISHING_PROTOCOL.md`,
`SKEPTIC_ARBITER.md`, `REPAIR_PROTOCOL.md`). Otherwise, run a
full-repo recompose.

Steps:

1. `bash scripts/check_drift.sh` — capture current hashes.
2. Spawn `module-composer` with the diff against `main` (or against
   the recorded baseline if no `main` exists yet) and the target
   canonical file `$1`. Brief: "propagate the substantive change into
   COMPOSED_AGENT.md and provider variants while preserving each
   format's idioms (XML tags for Claude, plain for ChatGPT, compact
   for API). Touch only the mirroring sections."
3. After `module-composer` returns, spawn `drift-checker` to confirm
   no derived file has unexpected divergence.
4. Surface the diff to the user. Do not commit — leave that to the
   user.