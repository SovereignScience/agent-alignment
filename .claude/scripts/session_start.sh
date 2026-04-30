#!/usr/bin/env bash
# SessionStart hook — surface project state at the top of context.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo '∅')"
last_commit="$(git log -1 --pretty='%h %s' 2>/dev/null || echo '')"
ahead="$(git rev-list --count main..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

short_hash() {
  [[ -f "$1" ]] && sha256sum "$1" 2>/dev/null | cut -c1-8 || echo "------"
}

ic="$(short_hash INNER_COMMONS_CORE.md)"
fp="$(short_hash FLOURISHING_PROTOCOL.md)"
sa="$(short_hash SKEPTIC_ARBITER.md)"
rp="$(short_hash REPAIR_PROTOCOL.md)"
ca="$(short_hash COMPOSED_AGENT.md)"
fc="$(short_hash FOR_CLAUDE.md)"
fg="$(short_hash FOR_CHATGPT.md)"
fa="$(short_hash FOR_API.md)"

cat <<EOF
agent-alignment session context (auto-loaded by .claude/scripts/session_start.sh):

  branch       $branch (${ahead:-0} ahead of main, ${dirty:-0} dirty)
  last commit  $last_commit

  canonical:
    INNER_COMMONS_CORE      $ic
    FLOURISHING_PROTOCOL    $fp
    SKEPTIC_ARBITER         $sa
    REPAIR_PROTOCOL         $rp

  derived:
    COMPOSED_AGENT          $ca
    FOR_CLAUDE              $fc
    FOR_CHATGPT             $fg
    FOR_API                 $fa

Specialist subagents in .claude/agents/ — see CLAUDE.md "Dispatch table".
Slash commands: /align-compose, /align-drift-check, /align-skeptic,
/align-repair, /align-flourishing-check, /align-scenario,
/align-add-module, /align-swarm-review.
EOF
