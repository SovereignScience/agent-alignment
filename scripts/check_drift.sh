#!/usr/bin/env bash
# Print sha256 short hashes for canonical + derived module files for
# both tracks. Caller decides whether the hash pattern looks consistent
# — this script only reports.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" 2>/dev/null || exit 0

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

printf "%-30s  %-14s  %s\n" "FILE" "SHA256(short)" "LAST COMMIT"
printf "%-30s  %-14s  %s\n" "----" "-------------" "-----------"

echo "[track A — SWE canonical]"
for f in SWE_CORE.md TESTING_PROTOCOL.md PERFORMANCE_PROTOCOL.md SECURITY_PROTOCOL.md; do
  printf "%-30s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[track B — alignment canonical]"
for f in INNER_COMMONS_CORE.md FLOURISHING_PROTOCOL.md SKEPTIC_ARBITER.md REPAIR_PROTOCOL.md; do
  printf "%-30s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[track B — alignment derived]"
for f in COMPOSED_AGENT.md FOR_CLAUDE.md FOR_CHATGPT.md FOR_API.md; do
  printf "%-30s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done

echo "[supporting]"
for f in README.md CLAUDE.md QUICKSTART_SWE.md QUICKSTART_FLOURISHING.md CONTRIBUTING.md; do
  printf "%-30s  %-14s  %s\n" "$f" "$(short_hash "$f")" "$(last_commit "$f")"
done
