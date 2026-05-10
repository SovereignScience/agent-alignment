#!/usr/bin/env bash
# Status line for the flourishing track. Shows branch, dirty count,
# and a short commitment over the four canonical alignment modules so
# any drift is visible at all times.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo '∅')"
ahead="$(git rev-list --count main..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

canon_short=""
if [[ -f INNER_COMMONS_CORE.md ]]; then
  canon_short="$(cat INNER_COMMONS_CORE.md FLOURISHING_PROTOCOL.md SKEPTIC_ARBITER.md REPAIR_PROTOCOL.md 2>/dev/null \
    | sha256sum | cut -c1-8)"
fi

c_dim=$'\033[2m'
c_yellow=$'\033[33m'
c_magenta=$'\033[35m'
c_off=$'\033[0m'

dirty_colored="${c_dim}${dirty}${c_off}"
[[ "$dirty" -gt 0 ]] && dirty_colored="${c_yellow}${dirty}${c_off}"

ahead_segment=""
[[ "$ahead" -gt 0 ]] && ahead_segment=" ${c_dim}↑${ahead}${c_off}"

canon_segment=""
[[ -n "$canon_short" ]] && canon_segment=" ${c_dim}align:${c_off}${c_magenta}${canon_short}${c_off}"

printf "flourishing ${c_dim}|${c_off} %s%s ${c_dim}|${c_off} ✎%s%s\n" \
  "$branch" "$ahead_segment" "$dirty_colored" "$canon_segment"
