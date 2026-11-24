#!/usr/bin/env bash
# Print sha256 short hashes for the four canonical alignment modules
# and the four derived provider variants, then fail when a derived file
# lacks a named item of a canonical module (check_drift.py has the rule).
set -euo pipefail
cd "$(dirname "$0")/.."

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

echo "[canonical]"
for f in INNER_COMMONS_CORE.md FLOURISHING_PROTOCOL.md SKEPTIC_ARBITER.md REPAIR_PROTOCOL.md; do
  printf "%-26s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[derived]"
for f in COMPOSED_AGENT.md FOR_CLAUDE.md FOR_CHATGPT.md FOR_API.md; do
  printf "%-26s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[supporting]"
for f in README.md CLAUDE.md; do
  printf "%-26s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

python3 scripts/check_drift.py
