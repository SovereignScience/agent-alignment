#!/usr/bin/env bash
# PostToolUse hook for Edit and Write, SWE track.
# Names the check that fits the edited file, and reminds the session when a
# protocol or a dependency manifest was touched. It runs no project tool:
# hooks run outside the sandbox, and a project's tools and their
# configuration are editable, so the session runs the named check itself as
# an ordinary sandboxed command. Never blocks. Output goes back to the model
# as additionalContext; PostToolUse stdout alone is only shown in the
# transcript.
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

# Protocols
case "$rel" in
  SWE_CORE.md|TESTING_PROTOCOL.md|PERFORMANCE_PROTOCOL.md|SECURITY_PROTOCOL.md|SKEPTIC_ARBITER.md)
    echo "post-edit-verify: protocol touched ($rel). Confirm the change names a concrete failure mode (CONTRIBUTING.md)."
    exit 0
    ;;
esac

# The file-level check to run from the session
case "$rel" in
  *.py)
    echo "post-edit-verify: Python changed ($rel); run ruff check on it, and mypy where the project configures it, then the affected tests."
    ;;
  *.ts|*.tsx)
    echo "post-edit-verify: TypeScript changed ($rel); run eslint on it and select the affected checks at the task checkpoint."
    ;;
  *.js|*.jsx|*.mjs|*.cjs)
    echo "post-edit-verify: JavaScript changed ($rel); run eslint on it."
    ;;
  *.rs)
    echo "post-edit-verify: Rust changed; select the affected package's checks at the task checkpoint."
    ;;
  *.go)
    echo "post-edit-verify: Go changed ($rel); run gofmt -l on it and select affected package checks at the task checkpoint."
    ;;
  *.c|*.cpp|*.h|*.hpp)
    echo "post-edit-verify: C or C++ changed ($rel); run clang-format --dry-run --Werror on it where the project uses it."
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
