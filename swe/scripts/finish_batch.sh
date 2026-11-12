#!/usr/bin/env bash
# Finish a batch of this kit's own tasks in one run: push, review, merge and
# test, publish, install, bring the boards up to date and close. Run it
# yourself; it asks before every decision that is yours.
#
#   finish_batch.sh --actor human:<name> [--project <dir>]... \
#       [--after-merge <ID>:<criterion>]... <ID> [<ID>...]
#
# The phases, each named in the output:
#   1 push and fetch  every task's linked branch and the board, then fetch
#   2 review          each task's head commit and a one-line summary; y records
#                     your approval against that exact commit, and an open
#                     thread is shown first so you can resolve it
#   3 merge and test  approved tasks only, in the order given, then the kit's
#                     checks on the merged files; nothing is pushed
#   4 publish         prints the push command for the integration branch and
#                     goes on once that branch is on the remote
#   5 install         switch_rules.sh from the main checkout, when this machine
#                     differs from it
#   6 boards          this board and each --project's, with board_update.sh
#   7 acceptance      the checks again on the pushed branch, evidence on each
#                     --after-merge criterion of a merged task, then close
#                     every task the review section would let you mark done;
#                     a flag that still asks you something is shown first
#
# A STOP ends the run with a nonzero exit and undoes nothing. A rerun goes
# on from there: what is already pushed, approved, merged, installed or
# closed is left as it is.
set -euo pipefail

work=$(mktemp -d)
trap 'code=$?; rm -rf "${work:?}"; echo "== finish_batch ended with exit $code"; exit "$code"' EXIT
stop() { echo "STOP: $*" >&2; exit 1; }
phase() { echo; echo "== Phase $1"; }

actor="" projects=() after=() ids=()
while [ $# -gt 0 ]; do
    case $1 in
        --actor) [ $# -ge 2 ] || stop "--actor needs a value"; actor=$2; shift 2 ;;
        --project) [ $# -ge 2 ] || stop "--project needs a folder"; projects+=("$2"); shift 2 ;;
        --after-merge) [ $# -ge 2 ] || stop "--after-merge needs <ID>:<criterion>"; after+=("$2"); shift 2 ;;
        -*) stop "unknown option $1" ;;
        *) ids+=("$1"); shift ;;
    esac
done
[[ $actor == human:?* ]] || stop "--actor is a person, human:<name>"
[ ${#ids[@]} -gt 0 ] || stop "name at least one task"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tools="$(dirname "$here")/tools/lattice-review"
command -v lattice >/dev/null || stop "lattice is not on PATH"
common=$(git -C "$here" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || stop "$here is not in a Git repository"
root=$(dirname "$common")
base=$(git -C "$root" config --get lattice-review.base || echo main)
[ "$(git -C "$root" branch --show-current)" = "$base" ] || stop "the main checkout at $root is not on $base"
[ -z "$(git -C "$root" status --porcelain --untracked-files=no)" ] || stop "the main checkout at $root has uncommitted changes"
for project in "${projects[@]}"; do
    [ -f "$project/.lattice/config.json" ] || stop "$project has no board"
done

board() { git -C "$root/.lattice" "$@"; }
board_sync() {
    [ -f "$root/.lattice/config.json" ] || stop "there is no board at $root"
    [ -z "$(board rev-parse --show-cdup 2>/dev/null || echo none)" ] || stop "the board at $root has no repository of its own"
    git -C "$root" check-ignore -q .lattice/config.json || stop "source Git can still see the board at $root"
    [ "$(board branch --show-current)" = main ] || stop "the board at $root is not on its main branch"
    ! board rev-parse -q --verify MERGE_HEAD >/dev/null || stop "a merge is in progress in the board at $root"
    local path
    for path in events tasks plans artifacts notes archive ids.json config.json context.md; do
        if [ -e "$root/.lattice/$path" ]; then board add -- "$path"; fi
    done
    board diff --cached --quiet || board commit -q -m "$1"
    if ! board remote get-url origin >/dev/null 2>&1; then echo "board: committed here; it has no remote"; return 0; fi
    board fetch -q origin main || stop "the board remote could not be reached; the board is committed here"
    board merge-base --is-ancestor FETCH_HEAD HEAD \
        || stop "the board remote has commits this machine lacks; merge them first, then run this again"
    if [ "$(board rev-parse HEAD)" != "$(board rev-parse FETCH_HEAD)" ]; then
        board push -q origin main || stop "the board push was refused"
    fi
    echo "board: on its remote at $(board rev-parse --short HEAD)"
}
review() {
    local action=$1; shift
    LATTICE_ROOT=$root python3 "$tools/owner_review.py" "$action" --repo "$root" --board "$root" --main "$base" "$@"
}
kit_checks=(
    'for d in swe/.claude/scripts swe/scripts swe/tools/lattice-review flourishing/.claude/scripts; do (cd "$d" && python3 -m unittest discover -s . -p "test_*.py") || exit 1; done'
    'bash swe/scripts/check_drift.sh'
    '[ ! -f swe/scripts/adr.py ] || python3 swe/scripts/adr.py check'
)

phase "1: push and fetch"
git -C "$root" fetch -q origin || stop "the remote could not be fetched"
review branches "${ids[@]}" > "$work/branches" || stop "the board could not name each task's branch"
while read -r sid branch <&3; do
    here_at=$(git -C "$root" rev-parse -q --verify "refs/heads/$branch" || true)
    there_at=$(git -C "$root" rev-parse -q --verify "refs/remotes/origin/$branch" || true)
    if [ -z "$here_at" ] && [ -z "$there_at" ]; then
        stop "$sid: $branch is neither here nor on the remote"
    elif [ -z "$here_at" ]; then
        git -C "$root" branch -q --no-track "$branch" "$there_at"
        echo "$sid: took $branch from the remote at ${there_at:0:12}"
    elif [ "$here_at" = "$there_at" ]; then
        echo "$sid: $branch is on the remote at ${here_at:0:12}"
    elif [ -z "$there_at" ] || git -C "$root" merge-base --is-ancestor "$there_at" "$here_at"; then
        git -C "$root" push -q origin "refs/heads/$branch:refs/heads/$branch" || stop "$sid: the push of $branch was refused"
        echo "$sid: pushed $branch at ${here_at:0:12}"
    elif git -C "$root" merge-base --is-ancestor "$here_at" "$there_at"; then
        git -C "$root" fetch -q . "refs/remotes/origin/$branch:refs/heads/$branch" \
            || stop "$sid: $branch is behind its remote and checked out in a worktree; update it there"
        echo "$sid: moved $branch up to the remote at ${there_at:0:12}"
    else
        stop "$sid: $branch and its remote have each moved; settle that first"
    fi
done 3< "$work/branches"
board_sync "chore(board): record local updates before the batch"

phase "2: review"
review approve --actor "$actor" "${ids[@]}"

phase "3: merge and test"
check_args=()
for check in "${kit_checks[@]}"; do check_args+=(--check "$check"); done
LATTICE_ROOT=$root python3 "$tools/merge_approved.py" --repo "$root" --board "$root" --main "$base" \
    --no-push --skip-unapproved "${check_args[@]}" "${ids[@]}" || stop "the merge phase stopped; the lines above say why"

phase "4: publish"
if [ "$(git -C "$root" rev-parse "$base")" != "$(git -C "$root" rev-parse "origin/$base")" ]; then
    echo "$base is merged and checked here, and not pushed. Publish it from another terminal:"
    echo "    git -C $root push origin $base"
    echo "If the push check asks \"Push anyway?\" because of the size, answer y."
    read -rp "Press Enter here once the push is done: " _ || true
    git -C "$root" fetch -q origin "$base" || stop "the remote could not be fetched"
    [ "$(git -C "$root" rev-parse "$base")" = "$(git -C "$root" rev-parse "origin/$base")" ] \
        || stop "$base is not on the remote yet; push it, then run this again"
fi
echo "$base is on the remote at $(git -C "$root" rev-parse --short "$base")"

phase "5: install"
if [ -f "$root/swe/scripts/switch_rules.sh" ]; then
    state=$(bash "$root/swe/scripts/switch_rules.sh" status 2>&1 || true)
    if grep -qE '^collision|install_isolation.sh stopped' <<<"$state"; then
        grep -E '^collision|stopped|^install_isolation' <<<"$state" | sed 's/^/    /'
        stop "the installer cannot go ahead; nothing was installed"
    elif grep -qE '^(== |would )' <<<"$state"; then
        echo "this machine differs from $base; installing (answer y, then your sudo password)"
        bash "$root/swe/scripts/switch_rules.sh" apply || stop "the install did not finish; run switch_rules.sh status to see where it stands"
        echo "installed; reload each editor window and start new sessions when this run ends"
    else
        echo "nothing to install; this machine already matches $base"
    fi
else
    echo "skipped: $base has no swe/scripts/switch_rules.sh"
fi

phase "6: boards"
problems=0
if [ -f "$root/swe/scripts/board_update.sh" ]; then
    for project in "$root" "${projects[@]}"; do
        echo "-- $project"
        (cd "$project" && bash "$root/swe/scripts/board_update.sh" --apply) \
            || { problems=1; echo "PROBLEM: the board in $project was not brought up to date"; }
    done
else
    echo "skipped: $base has no swe/scripts/board_update.sh yet"
fi

phase "7: acceptance"
if [ ${#after[@]} -gt 0 ]; then
    for check in "${kit_checks[@]}"; do
        (cd "$root" && PYTHONDONTWRITEBYTECODE=1 bash -c "$check") || stop "a check failed on $base; no evidence was recorded and nothing was closed"
    done
    review evidence --actor "$actor" --note "Met: the project's checks pass on $base after the merge. Checked: finish_batch.sh ran the four test suites, check_drift.sh and the decision record check in the main checkout at $(git -C "$root" rev-parse --short "$base"), which is pushed, and all passed. Not checked: anything beyond those commands. Remains: nothing for this criterion." "${after[@]}"
fi
review close --actor "$actor" "${ids[@]}"
board_sync "chore(board): record the batch's reviews, evidence and closures"

echo
echo "== Summary"
review summary "${ids[@]}"
[ "$problems" -eq 0 ] || stop "a board was not brought up to date; see phase 6"
