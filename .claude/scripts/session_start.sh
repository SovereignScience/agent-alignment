#!/usr/bin/env bash
# SessionStart hook (root). This is a router. Real work lives in
# the swe/ or flourishing/ subtree; each has its own .claude/.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
last_commit="$(git log -1 --pretty='%h %s' 2>/dev/null || echo '')"

cat <<EOF
agent-alignment (repo root): this folder is a router. Two tracks:

  swe/         agentic software-engineering toolkit
               (12 SWE subagents, 14 SWE slash commands, language-aware hooks)
               cd swe/ && cat README.md

  flourishing/ Inner Commons + Flourishing alignment-prompt library
               (10 alignment subagents, 8 align-* commands, drift checks)
               cd flourishing/ && cat README.md

This root has no agents, no commands, no language hooks. cd into a
track and re-open from there to load the right .claude/ context.

  branch       $branch
  last commit  $last_commit
EOF
