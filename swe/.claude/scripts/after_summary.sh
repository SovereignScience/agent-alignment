#!/bin/sh
PATH=/usr/bin:/bin
export PATH
# SessionStart on compact, resume or fork: restate what matters after context was rebuilt.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Context was just summarised, resumed or forked. Re-read the CLAUDE.md files that apply here. Resume only the last thing the user asked for, as quoted in the summary, and list anything else as not started. Public research and approved read-only integrations are allowed. Remote writes and administration are owner-run. When an action is blocked, stop, say what was blocked and why, give the user the exact command if the task needs it, and never retry it another way."}}
JSON
