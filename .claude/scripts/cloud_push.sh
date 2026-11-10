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
set -euo pipefail

die() { echo "cloud_push: $*" >&2; exit 1; }

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
    git -C "$board" push --no-follow-tags origin refs/heads/main:refs/heads/main
    exit 0
fi
[ $# -eq 0 ] || die "usage: $0 [--board]"

branch="$(git branch --show-current)"
[[ $branch =~ ^feature/[A-Z][A-Z0-9]{0,4}-[0-9]+-[a-z0-9][a-z0-9-]*$ ]] \
    || die "'$branch' is not a task branch (feature/<ID>-<slug>); nothing else is pushed from a session"
[ -z "$(git status --porcelain)" ] || die "uncommitted changes; commit them first"
git push --no-follow-tags origin "refs/heads/$branch:refs/heads/$branch"
