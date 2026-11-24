#!/usr/bin/env bash
# PreToolUse hook for Bash. Block destructive patterns the project never
# wants run silently. Exit 0 = allow. Exit 2 = block (stderr → Claude).
set -euo pipefail

input="$(cat)"
if ! cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
command=json.load(sys.stdin)["tool_input"]["command"]
if not isinstance(command, str):
    raise TypeError("command is not text")
print(command)
' 2>/dev/null)"; then
  {
    echo "pre-bash-guard: could not read the command from the hook input, so it is refused"
    echo "Say in one line what was blocked; do not retry or delegate it. Carry on with work that does not need it."
  } >&2
  exit 2
fi

[[ -z "$cmd" ]] && exit 0

fixed_patterns=(
  'rm -rf /'
  'rm -rf ~'
  'git push'
  'git push --force'
  'git push -f '
  '--no-verify'
  '--no-gpg-sign'
  'git reset --hard origin/main'
  'git reset --hard origin/master'
  'chmod -R 777'
  ':(){ :|:& };:'
)
for pat in "${fixed_patterns[@]}"; do
  if printf '%s' "$cmd" | grep -Fq -- "$pat"; then
    {
      echo "pre-bash-guard: blocked literal pattern '$pat'"
      echo "Say in one line what was blocked; do not retry or delegate it. Carry on with work that does not need it."
    } >&2
    exit 2
  fi
done

regex_patterns=(
  'rm -rf \*'
  '(curl|wget)[^|]+\|[[:space:]]*sudo'
  '(curl|wget)[^|]+\|[[:space:]]*(ba)?sh([[:space:]]|$)'
)
for pat in "${regex_patterns[@]}"; do
  if printf '%s' "$cmd" | grep -Eq -- "$pat"; then
    {
      echo "pre-bash-guard: blocked regex pattern '$pat'"
      echo "Say in one line what was blocked; do not retry or delegate it. Carry on with work that does not need it."
    } >&2
    exit 2
  fi
done

exit 0
