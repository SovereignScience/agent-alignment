#!/usr/bin/env bash
# PostToolUse hook for Edit and Write, SWE track.
# Runs the formatter or type checker that fits the edited file, and reminds
# the session when a protocol or a dependency manifest was touched. Never
# blocks. Output goes back to the model as additionalContext; PostToolUse
# stdout alone is only shown in the transcript.
set -uo pipefail
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

buf="$(mktemp)"
out="$(mktemp)"
emit() {
  if [[ -s "$buf" ]]; then
    python3 -c 'import json,sys
text=open(sys.argv[1]).read().strip()
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":text}}))' "$buf" >&3
  fi
  rm -f "$buf" "$out"
}
trap emit EXIT
exec 3>&1
exec >"$buf"

run_and_label() {
  local label="$1"; shift
  if "$@" >"$out" 2>&1; then
    echo "post-edit-verify ok: $label"
  else
    echo "post-edit-verify FAIL: $label"
    head -n 30 "$out"
  fi
}

# Protocols
case "$rel" in
  SWE_CORE.md|TESTING_PROTOCOL.md|PERFORMANCE_PROTOCOL.md|SECURITY_PROTOCOL.md|SKEPTIC_ARBITER.md)
    echo "post-edit-verify: protocol touched ($rel). Confirm the change names a concrete failure mode (CONTRIBUTING.md)."
    exit 0
    ;;
esac

# Formatters and type checkers; each runs only when installed
case "$rel" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      run_and_label "ruff $rel" ruff check -- "$rel"
    elif [[ -x ./.venv/bin/ruff ]]; then
      run_and_label "ruff $rel" ./.venv/bin/ruff check -- "$rel"
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
    if [[ -f tsconfig.json ]]; then
      echo "post-edit-verify: TypeScript changed; select affected checks at the task checkpoint."
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
    echo "post-edit-verify: Rust changed; select the affected package's checks at the task checkpoint."
    ;;
  *.go)
    if command -v gofmt >/dev/null 2>&1; then
      if gofmt -l "$rel" >"$out" 2>&1; then
        if [[ -s "$out" ]]; then
          echo "post-edit-verify FAIL: gofmt needs formatting: $rel"
        else
          echo "post-edit-verify ok: gofmt $rel"
        fi
      else
        echo "post-edit-verify FAIL: gofmt $rel"
        head -n 30 "$out"
      fi
    fi
    echo "post-edit-verify: Go changed; select affected package checks at the task checkpoint."
    ;;
  *.c|*.cpp|*.h|*.hpp)
    if command -v clang-format >/dev/null 2>&1; then
      run_and_label "clang-format check $rel" clang-format --dry-run --Werror "$rel"
    fi
    ;;
esac

# Dependency manifests
case "$rel" in
  package.json|package-lock.json|yarn.lock|pnpm-lock.yaml|pyproject.toml|requirements.txt|requirements*.txt|poetry.lock|uv.lock|Pipfile|Pipfile.lock|Cargo.toml|Cargo.lock|go.mod|go.sum)
    echo "post-edit-verify: dependency manifest touched ($rel). Review affected dependencies within the task scope; do not start another agent automatically."
    ;;
esac

# .claude files
case "$rel" in
  .claude/settings.json)
    if python3 -c "import json;json.load(open('.claude/settings.json'))" 2>/dev/null; then
      echo "post-edit-verify ok: settings.json is valid JSON"
    else
      echo "post-edit-verify FAIL: settings.json is not valid JSON; fix before continuing"
    fi
    ;;
  .claude/agents/*.md|.claude/commands/*.md)
    if head -n 1 "$rel" 2>/dev/null | grep -q '^---$'; then
      echo "post-edit-verify ok: frontmatter present in $rel"
    else
      echo "post-edit-verify FAIL: $rel has no YAML frontmatter (must start with ---)"
    fi
    ;;
  .claude/scripts/*.sh|scripts/*.sh)
    if bash -n "$rel" 2>"$out"; then
      echo "post-edit-verify ok: bash -n $rel"
    else
      echo "post-edit-verify FAIL: $rel has shell syntax errors:"
      head -n 10 "$out"
    fi
    ;;
esac

exit 0
