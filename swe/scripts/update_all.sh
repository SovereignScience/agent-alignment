#!/usr/bin/env bash
# Bring every project in the workspace up to date with this kit. Run it
# yourself, after switch_rules.sh apply:
#
#   update_all.sh [--skip <folder>]... [--yes] [--push]
#
# The workspace is SWE_WORKSPACE, else the folder this kit's main checkout
# is in. For each Git repository directly inside it, other than this kit and
# the folders named with --skip, it:
#   1. refreshes the kit's push check where it is installed, or where the old
#      agent-safety wrapper is, keeping the old copy as .bak, and asks before
#      installing it where there is no push hook (--yes installs without
#      asking). Another tool's push hook, or hooks that core.hooksPath takes
#      from elsewhere, are named and left alone;
#   2. finds copies of the kit's agents and slash commands in the
#      repository's own .claude folder that differ from the kit, and asks
#      before bringing them up to date (a project's copy wins over the one
#      installed for every project). It commits those files and nothing
#      else, unless something else is staged, they are not tracked or HEAD
#      is on no branch. With --push it pushes that commit when it is the
#      only one the branch's upstream lacks;
#   3. brings the board up to date with board_update.sh --apply where the
#      repository has one.
# It says first whether this machine's installed rules, agents and commands
# match the kit; installing them is switch_rules.sh apply, which needs sudo.
# It deletes nothing. Exits 1 when any project could not be brought up to date.
set -euo pipefail

die() { echo "update_all: $*" >&2; exit 1; }

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$swe/scripts/kit_files.sh"
kit_root="$(dirname "$(git -C "$swe" rev-parse --path-format=absolute --git-common-dir)")"
kit_physical="$(cd "$kit_root" && pwd -P)"
workspace="${SWE_WORKSPACE:-$(dirname "$kit_root")}"
skip=() yes=no push=no
while [ $# -gt 0 ]; do
    case $1 in
        --skip) [ $# -ge 2 ] || die "--skip needs a folder name"; skip+=("$2"); shift 2 ;;
        --yes) yes=yes; shift ;;
        --push) push=yes; shift ;;
        *) die "unknown argument $1; usage: $0 [--skip <folder>]... [--yes] [--push]" ;;
    esac
done
# The push hook installed before this kit's own: it runs an older copy of the
# push check from /etc/claude-code/hooks that nothing updates any more.
old_wrapper=23f9cb1e867513f69d570947f290386d14f06d39e185faa33b0f8744d89bae1b
[ -d "$workspace" ] || die "no workspace at $workspace"
stamp=$(date -u +%Y%m%dT%H%M%SZ)

state=0
bash "$swe/scripts/switch_rules.sh" status --exit-code >/dev/null 2>&1 || state=$?
case $state in
    0) echo "machine  the installed rules, agents and commands match the kit" ;;
    3) echo "machine  BEHIND: run bash $swe/scripts/switch_rules.sh apply, then restart every session" ;;
    *) echo "machine  could not tell (switch_rules.sh status exit $state); run it to see why" ;;
esac

problems=0
for root in "$workspace"/*/; do
    root=${root%/}
    name=$(basename "$root")
    [ ! -L "$root" ] || continue
    [ "$(cd "$root" && pwd -P)" != "$kit_physical" ] || continue
    skipped=no
    for s in "${skip[@]}"; do [ "$name" != "$s" ] || skipped=yes; done
    [ "$skipped" = no ] || continue
    [ -d "$root/.git" ] || continue
    echo
    echo "== $name"
    hooks=$(git -C "$root" rev-parse --path-format=absolute --git-path hooks)
    if [ "$hooks" != "$(cd "$root" && pwd -P)/.git/hooks" ]; then
        echo "note     its hooks come from $hooks (core.hooksPath); push check left alone"
    elif [ -L "$hooks/pre-push" ]; then
        echo "note     the push hook is a link (left alone)"
    elif [ ! -f "$hooks/pre-push" ]; then
        answer=$yes
        if [ "$yes" = no ]; then
            read -r -p "ask      no push hook here; install the kit's push check (your commits only, no AI tells, asks before large pushes)? [y/N] " answer || answer=""
        fi
        if [ "$answer" != y ] && [ "$answer" != yes ]; then
            echo "skipped  push check"
        elif mkdir -p "$hooks" && cp "$swe/.claude/scripts/pre-push" "$swe/.claude/scripts/tells_check.py" "$hooks/" \
                && chmod +x "$hooks/pre-push"; then
            echo "installed push check"
        else
            problems=$((problems + 1)); echo "PROBLEM  the push check could not be installed"
        fi
    elif ! grep -qF "$kit_hook_mark" "$hooks/pre-push" \
            && [ "$(sha256sum < "$hooks/pre-push" | cut -d' ' -f1)" != "$old_wrapper" ]; then
        echo "note     another tool's push hook is here (left alone)"
    elif cmp -s "$hooks/pre-push" "$swe/.claude/scripts/pre-push" && cmp -s "$hooks/tells_check.py" "$swe/.claude/scripts/tells_check.py"; then
        echo "current  push check"
    else
        done_ok=yes
        for h in pre-push tells_check.py; do
            if [ -f "$hooks/$h" ]; then cp -p "$hooks/$h" "$hooks/$h.$stamp.bak" || done_ok=no; fi
            cp "$swe/.claude/scripts/$h" "$hooks/$h" || done_ok=no
        done
        chmod +x "$hooks/pre-push" || done_ok=no
        if [ "$done_ok" = yes ]; then echo "updated  push check (old copies kept as *.$stamp.bak)"
        else problems=$((problems + 1)); echo "PROBLEM  the push check could not be updated; the .bak copies hold the old one"; fi
    fi
    stale=()
    for kind in agents commands; do
        for copy in "$root/.claude/$kind"/*.md; do
            [ -f "$copy" ] && [ ! -L "$copy" ] && [ -f "$swe/.claude/$kind/$(basename "$copy")" ] || continue
            cmp -s "$copy" <(render "$swe/.claude/$kind/$(basename "$copy")") || stale+=("$copy")
        done
    done
    if [ ${#stale[@]} -eq 0 ]; then
        echo "current  kit agents and commands in this project (or none)"
    else
        printf 'stale    %s\n' "${stale[@]#"$root"/}"
        answer=$yes
        if [ "$yes" = no ]; then
            read -r -p "ask      bring these ${#stale[@]} kit copies up to date? [y/N] " answer || answer=""
        fi
        if [ "$answer" = y ] || [ "$answer" = yes ]; then
            for copy in "${stale[@]}"; do
                render "$swe/.claude/$(basename "$(dirname "$copy")")/$(basename "$copy")" > "$copy"
            done
            echo "updated  ${#stale[@]} kit copies"
            files=("${stale[@]#"$root"/}")
            branch=$(git -C "$root" symbolic-ref -q --short HEAD || true)
            if [ -z "$branch" ]; then
                echo "note     not committed: HEAD is on no branch here; commit them yourself"
            elif ! git -C "$root" diff --cached --quiet; then
                echo "note     not committed: something else is already staged here"
            elif ! git -C "$root" ls-files --error-unmatch -- "${files[@]}" >/dev/null 2>&1; then
                echo "note     not committed: Git does not track them here"
            elif git -C "$root" diff --quiet HEAD -- "${files[@]}" 2>/dev/null; then
                echo "note     nothing to commit: HEAD already holds the kit copies"
            elif ! git -C "$root" commit -q -m "chore(agents): update the kit's agents and commands" -- "${files[@]}"; then
                # Naming the files keeps the commit to them, and Git refuses it during a merge.
                problems=$((problems + 1)); echo "PROBLEM  the kit copies could not be committed; the lines above say why"
            else
                echo "commit   $(git -C "$root" rev-parse --short HEAD) on $branch holds the kit copies"
                # Push to the upstream that the count is taken against, and only this branch,
                # whatever push.default or pushRemote say.
                remote=$(git -C "$root" config "branch.$branch.remote" || true)
                merge=$(git -C "$root" config "branch.$branch.merge" || true)
                ahead=$(git -C "$root" rev-list --count '@{u}..HEAD' 2>/dev/null || true)
                if [ -z "$remote" ] || [ -z "$merge" ] || [ -z "$ahead" ]; then
                    echo "note     not pushed: $branch has no upstream"
                elif [ "$push" = no ]; then
                    echo "note     not pushed; push it with: git -C $root push $remote HEAD:$merge"
                elif [ "$ahead" != 1 ]; then
                    echo "note     not pushed: $branch has $ahead commits its upstream lacks; check them, then push"
                elif git -C "$root" push -q "$remote" "HEAD:$merge"; then
                    echo "pushed   $branch to $remote"
                else
                    problems=$((problems + 1)); echo "PROBLEM  the push of $branch did not go through; the commit stays here"
                fi
            fi
        else
            echo "skipped  kit copies"
        fi
    fi
    if [ -f "$root/.lattice/config.json" ]; then
        (cd "$root" && bash "$swe/scripts/board_update.sh" --apply) \
            || { problems=$((problems + 1)); echo "PROBLEM  the board was not brought up to date; the lines above say why"; }
    else
        echo "note     no board here"
    fi
done
echo
if [ "$problems" -eq 0 ]; then
    echo "DONE: every project in $workspace is up to date"
else
    die "$problems project(s) could not be brought up to date; see PROBLEM above"
fi
