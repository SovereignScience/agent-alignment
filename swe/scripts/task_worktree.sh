#!/usr/bin/env bash
# Create and remove a board task's worktrees. Run it yourself: sessions under
# the managed profile cannot write Git metadata.
#
#   task_worktree.sh add <ID> <slug> [--candidates 2|3]
#   task_worktree.sh remove <ID> [--drop-unmerged] [--apply]
#
# add makes .worktrees/<ID> on feature/<ID>-<slug> from the base branch. With
# --candidates it makes .worktrees/<ID>-a, -b (and -c) on feature/<ID>-<slug>-a
# and so on, for competing versions of one task.
#
# remove shows what it would do and changes nothing without --apply. It removes
# the task's worktrees whose branch is merged into the base branch and deletes
# those branches. A worktree with uncommitted changes is always kept. A branch
# that is not merged is kept unless --drop-unmerged is given, which is how the
# candidates you did not pick are discarded, so run it after the merge. It
# never runs git worktree prune.
#
# The base branch is --base <branch>, else git config lattice-review.base,
# else main.
set -euo pipefail

usage() {
    echo "usage: $0 add <ID> <slug> [--candidates 2|3] [--base <branch>]" >&2
    echo "       $0 remove <ID> [--drop-unmerged] [--apply] [--base <branch>]" >&2
    exit 64
}
die() { echo "task_worktree: $*" >&2; exit 1; }

[ $# -ge 2 ] || usage
action=$1 id=$2
shift 2
[[ $id =~ ^[A-Z][A-Z0-9]{0,4}-[0-9]+$ ]] || die "a task ID looks like AA-12, not $id"
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || die "not inside a git repository"
root=$(dirname "$common")
base=$(git -C "$root" config --get lattice-review.base || echo main)
slug="" candidates=0 drop=no apply=no
if [ "$action" = add ]; then
    [ $# -ge 1 ] || usage
    slug=$1
    shift
fi
while [ $# -gt 0 ]; do
    case $1 in
        --base) [ $# -ge 2 ] || usage; base=$2; shift 2 ;;
        --candidates) [ $# -ge 2 ] || usage; candidates=$2; shift 2 ;;
        --drop-unmerged) drop=yes; shift ;;
        --apply) apply=yes; shift ;;
        *) usage ;;
    esac
done
git -C "$root" rev-parse --verify --quiet "$base^{commit}" >/dev/null || die "no base branch $base"

case $action in
add)
    [[ $slug =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "a slug is lowercase words joined by hyphens, not $slug"
    case $candidates in
        0) names=("") ;;
        2) names=(-a -b) ;;
        3) names=(-a -b -c) ;;
        *) die "--candidates takes 2 or 3" ;;
    esac
    mkdir -p "$common/info"
    grep -qxF /.worktrees/ "$common/info/exclude" 2>/dev/null || echo /.worktrees/ >> "$common/info/exclude"
    for name in "${names[@]}"; do
        git -C "$root" worktree add "$root/.worktrees/$id$name" -b "feature/$id-$slug$name" "$base"
    done
    if [ "$candidates" = 0 ]; then
        echo "Next: lattice branch-link $id feature/$id-$slug --actor agent:<tool>"
    else
        echo "Next: one session per worktree, each given the approved plan and none shown another's work."
        echo "Link only the branch you pick: lattice branch-link $id feature/$id-$slug-<letter> --actor human:<you>"
    fi
    ;;
remove)
    found=no
    for tree in "$root/.worktrees/$id" "$root/.worktrees/$id"-[a-c]; do
        [ -d "$tree" ] || continue
        found=yes
        branch=$(git -C "$tree" rev-parse --abbrev-ref HEAD)
        if [ "$branch" = HEAD ]; then
            echo "keep    $tree: no branch checked out"
        elif [ -n "$(git -C "$tree" status --porcelain)" ]; then
            echo "keep    $tree ($branch): uncommitted changes"
        elif git -C "$root" merge-base --is-ancestor "$branch" "$base"; then
            echo "remove  $tree ($branch): merged into $base"
            [ "$apply" = no ] || { git -C "$root" worktree remove "$tree"; git -C "$root" branch -d "$branch"; }
        elif [ "$drop" = yes ]; then
            echo "remove  $tree ($branch): not merged into $base, dropped on request"
            [ "$apply" = no ] || { git -C "$root" worktree remove "$tree"; git -C "$root" branch -D "$branch"; }
        else
            echo "keep    $tree ($branch): not merged into $base; --drop-unmerged discards it"
        fi
    done
    [ "$found" = yes ] || die "no worktree for $id under $root/.worktrees"
    [ "$apply" = yes ] || echo "Nothing changed. Rerun with --apply to do the lines marked remove."
    ;;
*) usage ;;
esac
