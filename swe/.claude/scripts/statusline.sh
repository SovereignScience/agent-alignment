#!/usr/bin/env bash
# Status line for the SWE track. Shows branch, dirty count, and a
# short commitment over the SWE canonical protocols so any drift is
# visible at a glance.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
ahead="$(git rev-list --count "$base"..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

swe_short=""
if [[ -f SWE_CORE.md ]]; then
  swe_short="$(cat SWE_CORE.md TESTING_PROTOCOL.md PERFORMANCE_PROTOCOL.md SECURITY_PROTOCOL.md SKEPTIC_ARBITER.md 2>/dev/null \
    | sha256sum | cut -c1-8)"
fi

c_dim=$'\033[2m'
c_yellow=$'\033[33m'
c_cyan=$'\033[36m'
c_off=$'\033[0m'

dirty_colored="${c_dim}${dirty}${c_off}"
[[ "$dirty" -gt 0 ]] && dirty_colored="${c_yellow}${dirty}${c_off}"

ahead_segment=""
[[ "$ahead" -gt 0 ]] && ahead_segment=" ${c_dim}+${ahead}${c_off}"

swe_segment=""
[[ -n "$swe_short" ]] && swe_segment=" ${c_dim}swe:${c_off}${c_cyan}${swe_short}${c_off}"

printf "swe ${c_dim}|${c_off} %s%s ${c_dim}|${c_off} dirty:%s%s\n" \
  "$branch" "$ahead_segment" "$dirty_colored" "$swe_segment"
