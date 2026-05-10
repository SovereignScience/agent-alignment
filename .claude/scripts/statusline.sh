#!/usr/bin/env bash
# Status line. Shows branch, dirty count, and short commitments over
# both Track A (SWE) and Track B (alignment) canonical modules so any
# drift is visible at all times.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo '∅')"
ahead="$(git rev-list --count main..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

# Short commitments — change only when canonical changes in either track.
swe_short=""
if [[ -f SWE_CORE.md ]]; then
  swe_short="$(cat SWE_CORE.md TESTING_PROTOCOL.md PERFORMANCE_PROTOCOL.md SECURITY_PROTOCOL.md 2>/dev/null \
    | sha256sum | cut -c1-6)"
fi

align_short=""
if [[ -f INNER_COMMONS_CORE.md ]]; then
  align_short="$(cat INNER_COMMONS_CORE.md FLOURISHING_PROTOCOL.md SKEPTIC_ARBITER.md REPAIR_PROTOCOL.md 2>/dev/null \
    | sha256sum | cut -c1-6)"
fi

c_dim=$'\033[2m'
c_yellow=$'\033[33m'
c_cyan=$'\033[36m'
c_magenta=$'\033[35m'
c_off=$'\033[0m'

dirty_colored="${c_dim}${dirty}${c_off}"
[[ "$dirty" -gt 0 ]] && dirty_colored="${c_yellow}${dirty}${c_off}"

ahead_segment=""
[[ "$ahead" -gt 0 ]] && ahead_segment=" ${c_dim}↑${ahead}${c_off}"

swe_segment=""
[[ -n "$swe_short" ]] && swe_segment=" ${c_dim}swe:${c_off}${c_cyan}${swe_short}${c_off}"

align_segment=""
[[ -n "$align_short" ]] && align_segment=" ${c_dim}align:${c_off}${c_magenta}${align_short}${c_off}"

printf "agent-alignment ${c_dim}|${c_off} %s%s ${c_dim}|${c_off} ✎%s%s%s\n" \
  "$branch" "$ahead_segment" "$dirty_colored" "$swe_segment" "$align_segment"
