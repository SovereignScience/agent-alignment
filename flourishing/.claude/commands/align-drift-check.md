---
description: Verify the four canonical modules and five derived files (COMPOSED_AGENT, FOR_CLAUDE, FOR_CHATGPT, FOR_API, README) are consistent. Hands off to drift-checker; never edits files.
allowed-tools: Bash, Read, Agent
model: inherit
---

Run the drift-checker against the working tree.

1. `bash scripts/check_drift.sh` — print per-file sha256 short hashes.
2. Spawn `drift-checker` with this brief: "audit canonical-vs-derived
   for substantive content drift. Report in the format defined in
   your agent definition. Do not edit. Verdict: IN-SYNC or
   NEEDS-COMPOSER."
3. Surface the report to the user.

If verdict is `NEEDS-COMPOSER`, recommend the user run
`/align-compose <changed-canonical>` next.