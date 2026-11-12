#!/usr/bin/env bash
# Bring a project's existing board up to date: its context with this kit's
# template, and its repository with the board's private remote. Run it
# yourself, from the top of the project:
#
#   board_update.sh            say what is behind; changes no file
#   board_update.sh --apply    do it
#
# --apply merges the template's changes into .lattice/context.md with
# board_context.py, commits the board's own changes, merges what the remote
# has and pushes. Two sides that wrote the same event log are merged line by
# line, and a task snapshot is rebuilt from its events. Anything else that
# changed on both sides, such as two sessions that each created a task, stops
# the merge before it is committed and names the file; the board's own
# changes stay committed and nothing is pushed. A board that holds a link, or
# whose .git is a file pointing to another repository, is left alone.
set -euo pipefail

die() { echo "board_update: $*" >&2; exit 1; }

apply=no
case "${1:-}" in
    "") ;;
    --apply) apply=yes ;;
    *) die "unknown argument $1; usage: $0 [--apply]" ;;
esac
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v lattice >/dev/null || die "lattice is not on PATH"
root=$(git rev-parse --show-toplevel 2>/dev/null) || die "this folder is not in a Git repository"
[ "$root" = "$PWD" ] || die "run this from the top of the repository: $root"
[ -f .lattice/config.json ] || die "this project has no board; board_setup.sh makes one"
# A link in the board, or a .git file that points to another repository, would
# take these writes into another project's board.
held=$(find -P .lattice -path .lattice/.git/objects -prune -o \
    \( -type l -o -type f -links +1 -o -path .lattice/.git -type f \) -print -quit)
[ -z "$held" ] || die "$held is a link, or points to another repository; nothing was done"
git check-ignore -q .lattice/config.json || die "source Git can still see the board"
board() { git -C .lattice "$@"; }
[ -z "$(board rev-parse --show-cdup 2>/dev/null || echo none)" ] \
    || die "the board has no repository of its own; see step 3b of LATTICE_ONBOARDING.md"
[ "$(board branch --show-current)" = main ] || die "the board is not on its main branch"
! board rev-parse -q --verify MERGE_HEAD >/dev/null || die "a merge is already in progress in .lattice"
doctor() { LATTICE_ROOT=$PWD LATTICE_NO_UPDATE_CHECK=1 lattice doctor >/dev/null 2>&1; }
kept=(events tasks plans artifacts notes archive ids.json config.json context.md .gitignore)

context=0
python3 "$here/board_context.py" "$([ "$apply" = yes ] && echo apply || echo status)" . || context=$?
[ "$context" -le 2 ] && { [ "$apply" = no ] || [ "$context" -ne 1 ]; } \
    || die "board_context.py failed (exit $context); nothing else was done"

remote=no
if board remote get-url origin >/dev/null 2>&1; then remote=yes; fi
if [ "$apply" = no ]; then
    echo "to commit  $(board status --porcelain -- "${kept[@]}" | wc -l) board file(s)"
    if [ "$remote" = no ]; then echo "no remote  the board is not pushed anywhere"
    elif board fetch -q origin main 2>/dev/null; then
        echo "to push    $(board rev-list --count FETCH_HEAD..HEAD) commit(s)"
        echo "to pull    $(board rev-list --count HEAD..FETCH_HEAD) commit(s)"
    else echo "no answer  the board remote could not be reached"; fi
    if doctor; then echo "healthy    lattice doctor finds nothing"; else echo "PROBLEM    lattice doctor reports a problem; run it here"; fi
    exit 0
fi

for path in "${kept[@]}"; do
    if [ -e ".lattice/$path" ]; then board add -- "$path"; fi
done
board diff --cached --quiet || board commit -q -m "chore(board): record local updates before sync"
if [ "$remote" = yes ]; then
    board fetch -q origin main || die "the board remote could not be reached; the board's changes are committed, nothing else changed"
    if board merge-base --is-ancestor FETCH_HEAD HEAD; then :
    elif board merge-base --is-ancestor HEAD FETCH_HEAD; then
        board merge -q --ff-only FETCH_HEAD || die "an uncommitted board file is in the way of the pull"
    else
        board merge --no-ff --no-commit FETCH_HEAD >/dev/null 2>&1 || true
        board rev-parse -q --verify MERGE_HEAD >/dev/null || die "the merge could not start; run git -C .lattice status"
        while IFS= read -r file; do
            if ! board show ":2:$file" >/dev/null 2>&1 || ! board show ":3:$file" >/dev/null 2>&1; then
                board merge --abort
                die "$file was deleted on one side and changed on the other; nothing was merged or pushed, and the board's own changes are committed"
            fi
            case $file in
                events/*.jsonl)
                    board show ":2:$file" > ".lattice/$file.ours"
                    board show ":3:$file" > ".lattice/$file.theirs"
                    python3 - ".lattice/$file.ours" ".lattice/$file.theirs" ".lattice/$file" <<'PY'
import json, sys
seen, rows = set(), []
for name in sys.argv[1:3]:
    for line in open(name):
        if line.strip() and line not in seen:
            seen.add(line)
            rows.append(line if line.endswith("\n") else line + "\n")
rows.sort(key=lambda line: json.loads(line).get("ts", ""))
open(sys.argv[3], "w").writelines(rows)
PY
                    rm ".lattice/$file.ours" ".lattice/$file.theirs"
                    board add -- "$file" ;;
                tasks/*.json) board checkout -q --ours -- "$file" ;;
                *) board merge --abort
                   die "$file changed on both sides; nothing was merged or pushed, and the board's own changes are committed" ;;
            esac
        done < <(board diff --name-only --diff-filter=U)
        LATTICE_ROOT=$PWD LATTICE_NO_UPDATE_CHECK=1 lattice rebuild --all >/dev/null \
            || { board merge --abort; die "lattice rebuild failed; nothing was merged"; }
        board add -- tasks
        doctor || { board merge --abort; die "lattice doctor found a problem after the merge; nothing was merged"; }
        board commit -q -m "chore(board): merge the remote board"
    fi
    board push -q origin main || die "the push failed; the board is merged here"
fi
doctor || die "lattice doctor reports a problem; run it here"
if [ "$remote" = yes ]; then where="in step with its remote at $(board rev-parse --short HEAD)"; else where="committed here, with no remote"; fi
case $context in
    0) echo "DONE: the board is $where" ;;
    *) echo "DONE, with the context left to resolve: the board is $where" ;;
esac
