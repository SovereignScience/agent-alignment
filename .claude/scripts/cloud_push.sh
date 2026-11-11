#!/usr/bin/env bash
# Push from a cloud session, where the owner has no shell of their own.
# Run it only when the owner asks for that push in the session.
#
#   bash .claude/scripts/cloud_push.sh           the current task branch
#   bash .claude/scripts/cloud_push.sh --board   the board's commits, to its main
#
# It refuses outside a cloud session, on any branch that is not
# feature/<ID>-<slug>, and with uncommitted changes. It never forces or
# deletes: a push that is not a fast-forward is rejected by Git.
# It also refuses any commit that is not the owner's or that carries AI
# attribution. A cloud container commits under the tool's own name until
# the owner sets the four Git identity variables on the environment, and
# published history is never rewritten, so this is checked before the push.
set -euo pipefail

die() { echo "cloud_push: $*" >&2; exit 1; }
checker="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../swe/.claude/scripts" 2>/dev/null && pwd || true)"

# Stop unless every commit about to leave the repository in $1 is the owner's.
owners_only() {
    local repo=$1 me others
    me="$(git -C "$repo" var GIT_AUTHOR_IDENT | sed 's/> .*/>/')"
    [ "$me" = "$(git -C "$repo" var GIT_COMMITTER_IDENT | sed 's/> .*/>/')" ] \
        || die "the author and committer identities differ; set GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, GIT_COMMITTER_NAME and GIT_COMMITTER_EMAIL together"
    if printf '%s' "$me" | grep -qiE '^(claude|codex|copilot|cursor|devin|gemini) <|<noreply@anthropic\.com>'; then
        die "this session commits as '$me', a tool's identity. The owner sets GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, GIT_COMMITTER_NAME and GIT_COMMITTER_EMAIL on the cloud environment; nothing was pushed"
    fi
    others="$(git -C "$repo" log --format='%an <%ae>%n%cn <%ce>' HEAD --not --remotes=origin | sort -u | grep -vixF "$me" || true)"
    [ -z "$others" ] || die "commits by $(printf '%s' "$others" | paste -sd, -) would leave; only the owner's commits are pushed from a session"
    [ -n "$checker" ] || die "the tell checker is missing, so commit messages cannot be checked; nothing was pushed"
    git -C "$repo" log --format=%B HEAD --not --remotes=origin | python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
from tells_check import find_tells
sys.exit(3 if "AI attribution" in find_tells(sys.stdin.read()) else 0)' "$checker" \
        || die "AI attribution in a commit message, or the tell checker could not run; nothing was pushed"
}

[ "${CLAUDE_CODE_REMOTE:-}" = true ] || die "not a cloud session; pushing is the owner's"
[ $# -le 1 ] || die "usage: $0 [--board]"

if [ "${1:-}" = --board ]; then
    root="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
    board="${LATTICE_ROOT:-$root}/.lattice"
    # The board must be the top of its own repository: from a plain folder
    # Git would walk up and push the source repository instead.
    [ -d "$board" ] && [ -z "$(git -C "$board" rev-parse --show-cdup 2>/dev/null || echo no)" ] \
        || die "no board repository of its own at $board"
    [ "$(git -C "$board" branch --show-current)" = main ] || die "the board is not on its main branch"
    [ -z "$(git -C "$board" status --porcelain)" ] || die "the board has uncommitted changes; commit them first"
    owners_only "$board"
    git -C "$board" push --no-follow-tags origin refs/heads/main:refs/heads/main
    exit 0
fi
[ $# -eq 0 ] || die "usage: $0 [--board]"

branch="$(git branch --show-current)"
[[ $branch =~ ^feature/[A-Z][A-Z0-9]{0,4}-[0-9]+-[a-z0-9][a-z0-9-]*$ ]] \
    || die "'$branch' is not a task branch (feature/<ID>-<slug>); nothing else is pushed from a session"
[ -z "$(git status --porcelain)" ] || die "uncommitted changes; commit them first"
owners_only .
git push --no-follow-tags origin "refs/heads/$branch:refs/heads/$branch"
