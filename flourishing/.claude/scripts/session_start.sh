#!/usr/bin/env bash
# SessionStart hook — surface the Inner Commons + Flourishing prompt
# stack at the top of context. This runs in the flourishing/ subtree
# only. The repo's other track (swe/) is independent and is not
# surfaced here.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
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
agent-alignment / flourishing: Inner Commons alignment-prompt library.

  branch       $branch (${ahead:-0} ahead of main, ${dirty:-0} dirty)
  last commit  $last_commit

You are in the alignment-prompt-authoring track. Canonical modules:
  INNER_COMMONS_CORE.md       $ic   relational layer (TRUST/CONSENT/ATTENTION/REPAIR)
  FLOURISHING_PROTOCOL.md     $fp   externalities + planetary stewardship
  SKEPTIC_ARBITER.md          $sa   anti-sycophancy on user-facing replies
  REPAIR_PROTOCOL.md          $rp   rupture detection + six-step repair

Derived (provider variants):
  COMPOSED_AGENT.md           $ca   all four in one drop-in
  FOR_CLAUDE.md               $fc   XML-tagged + abbreviated User-Preferences
  FOR_CHATGPT.md              $fg   ChatGPT system-prompt
  FOR_API.md                  $fa   API system-prompt + composition guidance

Subagents (.claude/agents/):
  inner-commons-steward · flourishing-auditor · skeptic · arbiter ·
  repair-coach · module-composer · drift-checker · scenario-evaluator ·
  prose-editor · pr-rubric-reviewer

Slash commands (.claude/commands/):
  /align-compose /align-drift-check /align-skeptic /align-repair
  /align-flourishing-check /align-scenario /align-add-module /align-swarm-review

Read this folder's README.md and CLAUDE.md for full conventions.
EOF
