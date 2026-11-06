#!/bin/sh
PATH=/usr/bin:/bin
export PATH
# SessionStart on compact, resume or fork: restate what matters after context was rebuilt.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Context was just summarised, resumed or forked. Re-read the CLAUDE.md files that apply here. Resume only the last thing the user asked for, as quoted in the summary, and list anything else as not started. Nothing leaves this machine, and a blocked action is a question for the user, not a command to hand over."}}
JSON
