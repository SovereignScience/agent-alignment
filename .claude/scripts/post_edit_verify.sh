#!/usr/bin/env bash
# PostToolUse hook for Edit / Write.
# Two jobs:
#   1. Track A (SWE): language-aware lint/typecheck on the edited file.
#   2. Track B (alignment): when a canonical module changes, remind to recompose.
# Never blocks (PostToolUse is advisory). Outputs to stdout so Claude
# sees the result on the next turn.
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

run_and_label() {
  local label="$1"; shift
  if "$@" >/tmp/align-hook.out 2>&1; then
    echo "post-edit-verify ✓ $label"
  else
    echo "post-edit-verify ✗ $label"
    head -n 30 /tmp/align-hook.out
  fi
}

# ─── Track B: canonical / derived alignment modules ────────────────
case "$rel" in
  INNER_COMMONS_CORE.md|FLOURISHING_PROTOCOL.md|SKEPTIC_ARBITER.md|REPAIR_PROTOCOL.md)
    echo "post-edit-verify: Track B canonical module touched ($rel)."
    echo "  → Run /align-compose $rel to propagate to derived files."
    echo "  → Or: bash scripts/check_drift.sh"
    exit 0
    ;;
  COMPOSED_AGENT.md|FOR_CLAUDE.md|FOR_CHATGPT.md|FOR_API.md)
    echo "post-edit-verify: Track B derived file touched ($rel)."
    echo "  → Run /align-drift-check to confirm canonical-vs-derived consistency."
    exit 0
    ;;
esac

# ─── Track A: SWE canonical protocols ──────────────────────────────
case "$rel" in
  SWE_CORE.md|TESTING_PROTOCOL.md|PERFORMANCE_PROTOCOL.md|SECURITY_PROTOCOL.md)
    echo "post-edit-verify: Track A canonical SWE protocol touched ($rel)."
    echo "  → Confirm the change names a concrete failure mode it targets (CONTRIBUTING.md)."
    echo "  → Consider running /swe-swarm-review before opening a PR."
    exit 0
    ;;
esac

# ─── Track A: language-aware lint / typecheck on edited file ───────
case "$rel" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      run_and_label "ruff $rel" ruff check "$rel" --select E,W,F --ignore E501
    elif [[ -x ./.venv/bin/ruff ]]; then
      run_and_label "ruff $rel" ./.venv/bin/ruff check "$rel" --select E,W,F --ignore E501
    fi
    if command -v mypy >/dev/null 2>&1 && [[ -f mypy.ini || -f pyproject.toml ]]; then
      run_and_label "mypy $rel" mypy "$rel"
    fi
    ;;

  *.ts|*.tsx)
    if command -v eslint >/dev/null 2>&1; then
      run_and_label "eslint $rel" eslint "$rel"
    elif [[ -x ./node_modules/.bin/eslint ]]; then
      run_and_label "eslint $rel" ./node_modules/.bin/eslint "$rel"
    fi
    if [[ -f tsconfig.json && -x ./node_modules/.bin/tsc ]]; then
      run_and_label "tsc --noEmit" ./node_modules/.bin/tsc --noEmit
    fi
    ;;

  *.js|*.jsx|*.mjs|*.cjs)
    if command -v eslint >/dev/null 2>&1; then
      run_and_label "eslint $rel" eslint "$rel"
    elif [[ -x ./node_modules/.bin/eslint ]]; then
      run_and_label "eslint $rel" ./node_modules/.bin/eslint "$rel"
    fi
    ;;

  *.rs)
    if command -v cargo >/dev/null 2>&1; then
      run_and_label "cargo check (workspace)" cargo check --quiet
    fi
    ;;

  *.go)
    if command -v gofmt >/dev/null 2>&1; then
      run_and_label "gofmt -d $rel" gofmt -d "$rel"
    fi
    if command -v go >/dev/null 2>&1; then
      run_and_label "go vet ./..." go vet ./...
    fi
    ;;

  *.c|*.cpp|*.h|*.hpp)
    if command -v clang-format >/dev/null 2>&1; then
      run_and_label "clang-format check $rel" clang-format --dry-run --Werror "$rel"
    fi
    ;;
esac

# ─── Dependency manifests — flag for dependency-auditor ────────────
case "$rel" in
  package.json|package-lock.json|yarn.lock|pnpm-lock.yaml)
    echo "post-edit-verify: dependency manifest touched ($rel)."
    echo "  → Run /swe-deps to audit CVEs, license drift, maintenance signal."
    ;;
  pyproject.toml|requirements.txt|requirements*.txt|poetry.lock|uv.lock|Pipfile|Pipfile.lock)
    echo "post-edit-verify: dependency manifest touched ($rel)."
    echo "  → Run /swe-deps to audit CVEs, license drift, maintenance signal."
    ;;
  Cargo.toml|Cargo.lock|go.mod|go.sum)
    echo "post-edit-verify: dependency manifest touched ($rel)."
    echo "  → Run /swe-deps to audit CVEs, license drift, maintenance signal."
    ;;
esac

# ─── .claude/ infrastructure ───────────────────────────────────────
case "$rel" in
  .claude/settings.json)
    if python3 -c "import json,sys;json.load(open('.claude/settings.json'))" 2>/dev/null; then
      echo "post-edit-verify ✓ settings.json is valid JSON"
    else
      echo "post-edit-verify ✗ settings.json is INVALID JSON — fix before continuing"
    fi
    ;;
  .claude/agents/*.md|.claude/commands/*.md)
    if head -n 1 "$rel" 2>/dev/null | grep -q '^---$'; then
      echo "post-edit-verify ✓ frontmatter present in $rel"
    else
      echo "post-edit-verify ✗ $rel missing YAML frontmatter (must start with ---)"
    fi
    ;;
  .claude/scripts/*.sh|scripts/*.sh)
    if bash -n "$rel" 2>/tmp/align-hook.err; then
      echo "post-edit-verify ✓ bash -n $rel"
    else
      echo "post-edit-verify ✗ $rel has shell syntax errors:"
      head -n 10 /tmp/align-hook.err
    fi
    ;;
esac

exit 0
