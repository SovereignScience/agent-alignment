#!/usr/bin/env bash
# SessionStart hook: surface the SWE protocol stack at the top of context.
# This runs in the swe/ subtree only. The repo's other track
# (flourishing/) is independent and is not surfaced here.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
last_commit="$(git log -1 --pretty='%h %s' 2>/dev/null || echo '')"
base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
ahead="$(git rev-list --count "$base"..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

short_hash() {
  [[ -f "$1" ]] && sha256sum "$1" 2>/dev/null | cut -c1-8 || echo "------"
}

sc="$(short_hash SWE_CORE.md)"
tp="$(short_hash TESTING_PROTOCOL.md)"
pp="$(short_hash PERFORMANCE_PROTOCOL.md)"
sp="$(short_hash SECURITY_PROTOCOL.md)"
ka="$(short_hash SKEPTIC_ARBITER.md)"

cat <<EOF
agent-alignment / swe: agentic software-engineering toolkit.

  branch       $branch (${ahead:-0} ahead of $base, ${dirty:-0} dirty)
  last commit  $last_commit

You are in the SWE track. Protocols (drop-in system prompts):
  SWE_CORE.md              $sc   read first; root cause; verify before done
  TESTING_PROTOCOL.md      $tp   focused checks; deterministic; behavior-focused
  PERFORMANCE_PROTOCOL.md  $pp   measure first; name the budget; idle costs nothing
  SECURITY_PROTOCOL.md     $sp   trust boundaries; OWASP; least privilege; fail closed
  SKEPTIC_ARBITER.md       $ka   anti-sycophancy on engineering claims

Subagents (.claude/agents/):
  code-reviewer, regression-test-writer, security-reviewer, perf-auditor,
  dashboard-probe, dependency-auditor, architecture-explorer,
  refactoring-planner, debugger, docs-writer, code-skeptic, code-arbiter

Slash commands (.claude/commands/):
  /swe-explore /swe-review /swe-add-test /swe-fix-bug /swe-debug
  /swe-perf /swe-security /swe-deps /swe-refactor /swe-probe /swe-docs
  /swe-skeptic /swe-swarm-review /swe-init

Read this folder's README.md and CLAUDE.md for full conventions.
EOF
