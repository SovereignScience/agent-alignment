#!/usr/bin/env bash
# SessionStart hook (root). Windows open here, at the main checkout: a
# session reaches only the folder it was opened in, and Git, the board
# and the task worktrees are here.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

branch="$(git branch --show-current 2>/dev/null || echo 'none')"
last_commit="$(git log -1 --pretty='%h %s' 2>/dev/null || echo '')"

cat <<EOF
agent-alignment (main checkout). Work from here: Git, the board and the
task worktrees under .worktrees/ are reachable from this folder only.

  swe/         agentic software-engineering toolkit: read swe/CLAUDE.md
  flourishing/ Inner Commons + Flourishing prompt library: read
               flourishing/CLAUDE.md

A track's agents and commands are not loaded here. Open the file under
<track>/.claude/agents or <track>/.claude/commands and follow it.

  branch       $branch
  last commit  $last_commit
EOF
