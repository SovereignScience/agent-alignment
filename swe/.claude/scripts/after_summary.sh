#!/bin/sh
PATH=/usr/bin:/bin
export PATH
# SessionStart on compact, resume or fork: restate what matters after context was rebuilt.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Context was just summarised, resumed or forked. Re-read the CLAUDE.md files that apply here. Resume only the last thing the user asked for, as quoted in the summary, and list anything else as not started. Public research and approved read-only integrations are allowed. Remote writes and administration are owner-run. When an action is blocked, tell the user in one line what was blocked and why you wanted it. If the task needs it, give the exact command for the user to run. Do not retry it another way. Carry on with the work that does not need it."}}
JSON
