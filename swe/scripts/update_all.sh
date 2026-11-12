#!/usr/bin/env bash
# Bring every project in the workspace up to date with this kit. Run it
# yourself, after switch_rules.sh apply:
#
#   update_all.sh [--skip <folder>]... [--yes] [--push]
#
# The workspace is SWE_WORKSPACE, else the folder this kit's main checkout
# is in. For each Git repository directly inside it, other than this kit, the
# folders named with --skip and those listed in ~/.config/agent-alignment/skip
# (one name a line), it:
#   1. refreshes the kit's push check where it is installed, or where the old
#      agent-safety wrapper is, keeping the old copy as .bak, and asks before
#      installing it where there is no push hook (--yes installs without
#      asking). Another tool's push hook, or hooks that core.hooksPath takes
#      from elsewhere, are named and left alone;
#   2. finds copies of the kit's agents and slash commands in the
#      repository's own .claude folder that differ from the kit's files, and
#      asks before bringing them up to date (a project's copy wins over the one
#      installed for every project, and holds no path from this machine). A
#      tracked copy with uncommitted edits
#      is left alone; an untracked one keeps its old text as .bak. It
#      commits those files and nothing else, and only on the branch that
#      tracks its remote's default branch; it does not commit when
#      something else is staged, they are not tracked, HEAD is on no branch
#      or a merge, rebase, cherry-pick or revert is in progress. With
#      --push it pushes that commit when it is the only one the branch's
#      upstream lacks and the branch pushes to that upstream; the push
#      check may ask at the terminal, once a repository;
#   3. brings the board up to date with board_update.sh --apply where the
#      repository has one.
# It says first whether this machine's installed rules, agents and commands
# match the kit; installing them is switch_rules.sh apply, which needs sudo.
# It stops before any project when there is neither that file nor --skip, or
# when a name to leave out matches no folder; an empty file leaves out nothing.
# A project whose Git files could take a write elsewhere (git_elsewhere.sh) is
# named and left alone. Where
# .claude/agents, .claude/commands or .lattice is a link, or a push hook file is,
# it names it and leaves that part alone. It replaces a file by renaming a new
# one over it, so a hard link elsewhere keeps its text. Its push sends no tags,
# whatever push.followTags says.
# It deletes nothing. Exits 1 when any project could not be brought up to date.
set -euo pipefail

die() { echo "update_all: $*" >&2; exit 1; }

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$swe/scripts/kit_files.sh"
source "$swe/scripts/git_elsewhere.sh"
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
skip_file="$HOME/.config/agent-alignment/skip"
if [ -f "$skip_file" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line#"${line%%[![:space:]]*}"} && line=${line%"${line##*[![:space:]]}"} && line=${line%/}
        [ -z "$line" ] || skip+=("$line")
    done < "$skip_file"
elif [ ${#skip[@]} -eq 0 ]; then
    die "no $skip_file: name the folders to leave out there, one a line; an empty file leaves out nothing"
fi
# The push hook installed before this kit's own: it runs an older copy of the
# push check from /etc/claude-code/hooks that nothing updates any more.
old_wrapper=23f9cb1e867513f69d570947f290386d14f06d39e185faa33b0f8744d89bae1b
[ -d "$workspace" ] || die "no workspace at $workspace"
workspace=$(cd "$workspace" && pwd -P)
for s in "${skip[@]}"; do
    [ "$s" = "${s##*/}" ] && [ -e "$workspace/$s" ] \
        || die "nothing in $workspace is named $s; correct it in --skip or $skip_file"
done
echo "skip     ${skip[*]:-nothing}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)

state=0
bash "$swe/scripts/switch_rules.sh" status --exit-code >/dev/null 2>&1 || state=$?
case $state in
    0) echo "machine  the installed rules, agents and commands match the kit" ;;
    3) echo "machine  BEHIND: run bash $swe/scripts/switch_rules.sh apply, then restart every session" ;;
    *) echo "machine  could not tell (switch_rules.sh status exit $state); run it to see why" ;;
esac

# A part of the project being updated that is a link or not a plain folder, so
# writes there could land in another project, perhaps a skipped one. $root is a
# physical path, so any link shows as a difference.
linked() {
    { [ -e "$1" ] || [ -L "$1" ]; } && [ "$(cd "$1" 2>/dev/null && pwd -P)" != "$1" ] || return 1
    echo "note     ${1#"$root"/} is a link or not a plain folder; left alone"
}
# Put the kit's file $1 in place of $2 by renaming a new file over it, so a hard
# link to $2 from elsewhere keeps its old text.
replace() { cp "$1" "$2.$stamp.new" && mv -f "$2.$stamp.new" "$2"; }

problems=0
for root in "$workspace"/*/; do
    root=${root%/}
    name=$(basename "$root")
    skipped=no
    for s in "${skip[@]}"; do [ "$name" != "$s" ] || skipped=yes; done
    [ "$skipped" = no ] || continue
    [ ! -L "$root" ] || continue
    [ "$(cd "$root" && pwd -P)" != "$kit_physical" ] || continue
    [ -d "$root/.git" ] || continue
    echo
    echo "== $name"
    if held=$(git_elsewhere "$root"); then
        echo "note     $held; this project is left alone"
        continue
    fi
    hooks=$(git -C "$root" rev-parse --path-format=absolute --git-path hooks)
    if [ "$hooks" != "$root/.git/hooks" ]; then
        echo "note     its hooks come from $hooks (core.hooksPath); push check left alone"
    elif [ -L "$hooks/pre-push" ] || [ -L "$hooks/tells_check.py" ]; then
        echo "note     the push hook or tells_check.py is a link (left alone)"
    elif [ ! -f "$hooks/pre-push" ]; then
        answer=$yes
        if [ "$yes" = no ]; then
            read -r -p "ask      no push hook here; install the kit's push check (your commits only, no AI tells, asks before large pushes)? [y/N] " answer || answer=""
        fi
        if [ "$answer" != y ] && [ "$answer" != yes ]; then
            echo "skipped  push check"
        elif mkdir -p "$hooks" && replace "$swe/.claude/scripts/pre-push" "$hooks/pre-push" \
                && replace "$swe/.claude/scripts/tells_check.py" "$hooks/tells_check.py" && chmod +x "$hooks/pre-push"; then
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
            replace "$swe/.claude/scripts/$h" "$hooks/$h" || done_ok=no
        done
        chmod +x "$hooks/pre-push" || done_ok=no
        if [ "$done_ok" = yes ]; then echo "updated  push check (old copies kept as *.$stamp.bak)"
        else problems=$((problems + 1)); echo "PROBLEM  the push check could not be updated; the .bak copies hold the old one"; fi
    fi
    stale=() edited=()
    for kind in agents commands; do
        ! linked "$root/.claude/$kind" || continue
        for copy in "$root/.claude/$kind"/*.md; do
            [ -f "$copy" ] && [ ! -L "$copy" ] && [ -f "$swe/.claude/$kind/$(basename "$copy")" ] || continue
            ! cmp -s "$copy" "$swe/.claude/$kind/$(basename "$copy")" || continue
            if git -C "$root" ls-files --error-unmatch -- "$copy" >/dev/null 2>&1 \
                    && ! git -C "$root" diff --quiet HEAD -- "$copy" 2>/dev/null; then
                edited+=("$copy")
            else
                stale+=("$copy")
            fi
        done
    done
    if [ ${#edited[@]} -gt 0 ]; then
        printf 'kept     %s: it has uncommitted edits; bring it up to date yourself\n' "${edited[@]#"$root"/}"
    fi
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
                # Git holds the old text of a tracked copy; an untracked one keeps it beside it.
                if ! git -C "$root" ls-files --error-unmatch -- "$copy" >/dev/null 2>&1; then
                    cp -p "$copy" "$copy.$stamp.bak"
                fi
                replace "$swe/.claude/$(basename "$(dirname "$copy")")/$(basename "$copy")" "$copy"
            done
            echo "updated  ${#stale[@]} kit copies"
            files=("${stale[@]#"$root"/}")
            branch=$(git -C "$root" symbolic-ref -q --short HEAD || true)
            busy=""
            for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
                [ ! -e "$(git -C "$root" rev-parse --path-format=absolute --git-path "$state")" ] || busy=$state
            done
            # The kit commit goes only on the branch the remote calls its default, never
            # into work on another branch.
            remote="" merge="" upstream="" default=""
            if [ -n "$branch" ]; then
                remote=$(git -C "$root" config "branch.$branch.remote" || true)
                merge=$(git -C "$root" config "branch.$branch.merge" || true)
                upstream=$(git -C "$root" rev-parse --symbolic-full-name '@{u}' 2>/dev/null || true)
                [ -z "$remote" ] || [ "$remote" = . ] \
                    || default=$(git -C "$root" symbolic-ref -q "refs/remotes/$remote/HEAD" || true)
            fi
            if [ -z "$branch" ]; then
                echo "note     not committed: HEAD is on no branch here; commit them yourself"
            elif [ -n "$busy" ]; then
                echo "note     not committed: Git is in the middle of an operation here ($busy); commit them yourself"
            elif ! git -C "$root" diff --cached --quiet; then
                echo "note     not committed: something else is already staged here"
            elif ! git -C "$root" ls-files --error-unmatch -- "${files[@]}" >/dev/null 2>&1; then
                echo "note     not committed: Git does not track them here; untracked copies kept their old text as *.$stamp.bak"
            elif [ -z "$remote" ] || [ "$remote" = . ]; then
                echo "note     not committed: $branch tracks no remote branch; commit them yourself"
            elif [ -z "$default" ]; then
                echo "note     not committed: the default branch of $remote is not known here (git remote set-head $remote --auto sets it); commit them yourself"
            elif [ "$upstream" != "$default" ]; then
                echo "note     not committed: $branch is not the default branch of $remote (${default#refs/remotes/}); commit them yourself"
            elif ! git -C "$root" commit -q -m "chore(agents): update the kit's agents and commands" -- "${files[@]}"; then
                problems=$((problems + 1)); echo "PROBLEM  the kit copies could not be committed; the lines above say why"
            else
                echo "commit   $(git -C "$root" rev-parse --short HEAD) on $branch holds the kit copies"
                # Push only where this branch's pushes go to the upstream the count is taken
                # against, and name the one ref, whatever push.default says.
                pushes_to=$(git -C "$root" rev-parse --symbolic-full-name '@{push}' 2>/dev/null || true)
                ahead=$(git -C "$root" rev-list --count '@{u}..HEAD')
                if [ "$pushes_to" != "$upstream" ]; then
                    echo "note     not pushed: pushes from $branch do not go to its upstream $upstream; push it yourself"
                elif [ "$push" = no ]; then
                    echo "note     not pushed; push it with: git -C $root push --no-follow-tags $remote HEAD:$merge"
                elif [ "$ahead" != 1 ]; then
                    echo "note     not pushed: $branch has $ahead commits its upstream lacks; check them, then push"
                elif git -C "$root" push -q --no-follow-tags "$remote" "HEAD:$merge"; then
                    echo "pushed   $branch to $remote"
                else
                    problems=$((problems + 1)); echo "PROBLEM  the push of $branch did not go through; the commit stays here"
                fi
            fi
        else
            echo "skipped  kit copies"
        fi
    fi
    if linked "$root/.lattice"; then
        :
    elif [ -f "$root/.lattice/config.json" ]; then
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
