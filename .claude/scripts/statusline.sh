#!/usr/bin/env bash
# Status line for the repo root. Reminds the agent this is a router.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
ahead="$(git rev-list --count "$base"..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

c_dim=$'\033[2m'
c_yellow=$'\033[33m'
c_off=$'\033[0m'

dirty_colored="${c_dim}${dirty}${c_off}"
[[ "$dirty" -gt 0 ]] && dirty_colored="${c_yellow}${dirty}${c_off}"

ahead_segment=""
[[ "$ahead" -gt 0 ]] && ahead_segment=" ${c_dim}+${ahead}${c_off}"

printf "agent-alignment ${c_dim}(main checkout)${c_off} ${c_dim}|${c_off} %s%s ${c_dim}|${c_off} dirty:%s ${c_dim}tracks: swe/ flourishing/${c_off}\n" \
  "$branch" "$ahead_segment" "$dirty_colored"
