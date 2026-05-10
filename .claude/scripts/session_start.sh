#!/usr/bin/env bash
# SessionStart hook — surface project state at the top of context.
# Shows both tracks (SWE + alignment) so a fresh agent knows immediately
# what kind of repo this is and which files matter.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo '∅')"
last_commit="$(git log -1 --pretty='%h %s' 2>/dev/null || echo '')"
ahead="$(git rev-list --count main..HEAD 2>/dev/null || echo 0)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

short_hash() {
  [[ -f "$1" ]] && sha256sum "$1" 2>/dev/null | cut -c1-8 || echo "------"
}

# Track A
sc="$(short_hash SWE_CORE.md)"
tp="$(short_hash TESTING_PROTOCOL.md)"
pp="$(short_hash PERFORMANCE_PROTOCOL.md)"
sp="$(short_hash SECURITY_PROTOCOL.md)"

# Track B
ic="$(short_hash INNER_COMMONS_CORE.md)"
fp="$(short_hash FLOURISHING_PROTOCOL.md)"
sa="$(short_hash SKEPTIC_ARBITER.md)"
rp="$(short_hash REPAIR_PROTOCOL.md)"

cat <<EOF
agent-alignment session context (auto-loaded by .claude/scripts/session_start.sh):

  branch       $branch (${ahead:-0} ahead of main, ${dirty:-0} dirty)
  last commit  $last_commit

This repo ships TWO tracks. Pick the one you need:

  Track A — agentic software engineering (primary)
    QUICKSTART_SWE.md            ← read this if you're doing coding work
    SWE_CORE.md                   $sc
    TESTING_PROTOCOL.md           $tp
    PERFORMANCE_PROTOCOL.md       $pp
    SECURITY_PROTOCOL.md          $sp
    Subagents: code-reviewer, regression-test-writer, security-reviewer,
               perf-auditor, dashboard-probe, dependency-auditor,
               architecture-explorer, refactoring-planner, debugger,
               docs-writer
    Slash commands: /swe-explore /swe-review /swe-add-test /swe-fix-bug
                    /swe-debug /swe-perf /swe-security /swe-deps
                    /swe-refactor /swe-probe /swe-docs /swe-swarm-review
                    /swe-init

  Track B — Inner Commons + Flourishing alignment (prompt library)
    QUICKSTART_FLOURISHING.md    ← read this if you're authoring alignment prompts
    INNER_COMMONS_CORE.md         $ic
    FLOURISHING_PROTOCOL.md       $fp
    SKEPTIC_ARBITER.md            $sa
    REPAIR_PROTOCOL.md            $rp
    Subagents: inner-commons-steward, flourishing-auditor, skeptic, arbiter,
               repair-coach, module-composer, drift-checker,
               scenario-evaluator, prose-editor, pr-rubric-reviewer
    Slash commands: /align-compose /align-drift-check /align-skeptic
                    /align-repair /align-flourishing-check /align-scenario
                    /align-add-module /align-swarm-review

Project conventions: CLAUDE.md
EOF
