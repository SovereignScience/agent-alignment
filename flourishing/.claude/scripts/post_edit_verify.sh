#!/usr/bin/env bash
# PostToolUse hook for Edit / Write — flourishing track.
# When a canonical module changes, remind to recompose. When a derived
# file changes alone, suggest a drift check. Validate .claude/* edits.
# Never blocks (PostToolUse is advisory).
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

input="$(cat)"
file_path="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    ti=d.get("tool_input",{})
    print(ti.get("file_path") or ti.get("path") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")"

[[ -z "$file_path" ]] && exit 0
rel="${file_path#$PWD/}"

case "$rel" in
  INNER_COMMONS_CORE.md|FLOURISHING_PROTOCOL.md|SKEPTIC_ARBITER.md|REPAIR_PROTOCOL.md)
    echo "post-edit-verify: canonical alignment module touched ($rel)."
    echo "  - Run /align-compose $rel to propagate to derived files."
    echo "  - Or: bash scripts/check_drift.sh"
    ;;
  COMPOSED_AGENT.md|FOR_CLAUDE.md|FOR_CHATGPT.md|FOR_API.md)
    echo "post-edit-verify: derived file touched ($rel)."
    echo "  - Run /align-drift-check to confirm canonical-vs-derived consistency."
    ;;
  .claude/settings.json)
    if python3 -c "import json,sys;json.load(open('.claude/settings.json'))" 2>/dev/null; then
      echo "post-edit-verify ok: settings.json is valid JSON"
    else
      echo "post-edit-verify FAIL: settings.json is INVALID JSON, fix before continuing"
    fi
    ;;
  .claude/agents/*.md|.claude/commands/*.md)
    if head -n 1 "$rel" 2>/dev/null | grep -q '^---$'; then
      echo "post-edit-verify ok: frontmatter present in $rel"
    else
      echo "post-edit-verify FAIL: $rel missing YAML frontmatter (must start with ---)"
    fi
    ;;
  .claude/scripts/*.sh|scripts/*.sh)
    if bash -n "$rel" 2>/tmp/align-hook.err; then
      echo "post-edit-verify ok: bash -n $rel"
    else
      echo "post-edit-verify FAIL: $rel has shell syntax errors:"
      head -n 10 /tmp/align-hook.err
    fi
    ;;
esac

exit 0
