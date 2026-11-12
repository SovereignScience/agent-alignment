#!/usr/bin/env bash
# Print sha256 short hashes for the SWE canonical protocols + supporting
# docs in this subtree. Exits 1 when one of them is missing; whether the
# hashes look consistent is for the caller to judge.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
missing=0

short_hash() {
  if [[ -f "$1" ]]; then
    sha256sum "$1" | cut -c1-12
  else
    echo "MISSING-FILE"
  fi
}

last_commit() {
  git log -1 --pretty='%h %ar' -- "$1" 2>/dev/null || echo "(no git history)"
}

printf "%-26s  %-14s  %s\n" "FILE" "SHA256(short)" "LAST COMMIT"
printf "%-26s  %-14s  %s\n" "----" "-------------" "-----------"

echo "[canonical SWE protocols]"
for f in SWE_CORE.md TESTING_PROTOCOL.md PERFORMANCE_PROTOCOL.md SECURITY_PROTOCOL.md SKEPTIC_ARBITER.md; do
  [[ -f "$f" ]] || missing=$((missing + 1))
  printf "%-26s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[supporting]"
for f in README.md CLAUDE.md; do
  [[ -f "$f" ]] || missing=$((missing + 1))
  printf "%-26s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done
if (( missing )); then
  echo "check_drift: $missing file(s) missing" >&2
  exit 1
fi
