#!/usr/bin/env bash
# Try this checkout's rules on this machine, then go back. Run it yourself in a
# terminal, from the checkout you want to try; sessions cannot write these files.
#
#   swe/scripts/switch_rules.sh status [--exit-code]      what would change; writes nothing
#   swe/scripts/switch_rules.sh apply [--context <file>]  save what is installed, then install this checkout
#   swe/scripts/switch_rules.sh revert [<snapshot>]       put a saved state back
#
# apply first saves every file it may touch under
# ~/.config/agent-alignment/snapshots/<time>/. Then it:
#   1. runs install_isolation.sh --apply: the managed settings, hooks and Codex profile;
#   2. merges this checkout's changes to the user rules template (user/CLAUDE.md)
#      into ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md, keeping what you filled in;
#   3. copies codex/default.rules to ~/.codex/rules/, if ~/.codex exists;
#   4. refreshes the pre-push hook in this repository, if one is installed;
#   5. with --context, installs that file as this repository's board context.
# status --exit-code also answers by exit status, for a script: 0 when apply
# would change nothing, 1 when it would change something, 2 when it could not
# go ahead.
# revert restores each saved file and removes any that did not exist when the
# snapshot was taken. With no name it goes back to the state before the first
# apply that has not been reverted, however many times apply ran since, and
# refuses when there is no such apply. Name a snapshot folder to go to that one. Restart every Claude Code and Codex
# session after either.
#
# Template changes are worked out against the version each installed copy was
# made from: the committed version of user/CLAUDE.md it differs from least, or
# SWE_RULES_BASE when set. A change that collides with your own edits stops
# apply before anything is written.
# SWE_WORKSPACE is the folder that holds your checkouts. install_isolation.sh
# needs it; unset, it is taken to be the folder this checkout is in.
# SWE_ETC and SWE_CODEX_ETC replace /etc/claude-code and /etc/codex, for tests.
set -euo pipefail

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
etc="${SWE_ETC:-/etc/claude-code}"
codex_etc="${SWE_CODEX_ETC:-/etc/codex}"
store="$HOME/.config/agent-alignment/snapshots"
marker="$HOME/.config/agent-alignment/before"
common="$(git -C "$swe" rev-parse --path-format=absolute --git-common-dir)"
root="$(dirname "$common")"
hooks="$common/hooks"
template="$swe/user/CLAUDE.md"
rules=("$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md")
codex_rules="$HOME/.codex/rules/default.rules"
files=(
    "$etc/managed-settings.json" "$etc/managed-settings.d/50-local.json"
    "$etc/hooks/guard_outward.py" "$etc/hooks/tells_check.py"
    "$etc/hooks/after_summary.sh" "$etc/hooks/fetch_allow.txt"
    "$codex_etc/requirements.toml"
    "$HOME/.claude/settings.json" "$HOME/.codex/config.toml" "${rules[@]}" "$codex_rules"
    "$hooks/pre-push" "$hooks/tells_check.py" "$root/.lattice/context.md"
)

usage() {
    echo "usage: $0 status [--exit-code] | apply [--context <file>] | revert [<snapshot>]" >&2
    exit 64
}
die() { echo "switch_rules: $*" >&2; exit 1; }
known() { local f; for f in "${files[@]}"; do [ "$f" != "$1" ] || return 0; done; return 1; }
managed() { case "$1" in "$etc"/*|"$codex_etc"/*) return 0 ;; *) return 1 ;; esac; }
latest_snapshot() { { find "$store" -mindepth 1 -maxdepth 1 -type d 2>/dev/null || true; } | sort | tail -n 1; }
# The snapshot a plain revert goes back to: the one taken before the first
# apply that has not been reverted. Empty when nothing is applied.
revert_target() {
    local name
    name="$(basename "$(cat "$marker" 2>/dev/null || true)")"
    if [ -n "$name" ] && [ -f "$store/$name/manifest" ]; then echo "$store/$name"; fi
}
# The committed template version an installed copy was made from.
base_of() {
    local file=$1 rev best="" least="" n
    if [ -n "${SWE_RULES_BASE:-}" ]; then
        git -C "$swe" show "$SWE_RULES_BASE:./user/CLAUDE.md" 2>/dev/null \
            || die "no user rules template at $SWE_RULES_BASE"
        return
    fi
    for rev in $(git -C "$swe" log --format=%H -- user/CLAUDE.md); do
        n=$(git -C "$swe" show "$rev:./user/CLAUDE.md" | diff - "$file" | grep -c '^[<>]' || true)
        if [ -z "$least" ] || [ "$n" -lt "$least" ]; then least=$n best=$rev; fi
    done
    [ -n "$best" ] || die "no committed user rules template in this checkout; set SWE_RULES_BASE"
    git -C "$swe" show "$best:./user/CLAUDE.md"
}

export SWE_WORKSPACE="${SWE_WORKSPACE:-$(dirname "$root")}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# The installed rules with this checkout's template changes merged in, one
# file per installed copy. Returns 1 when a change collides with local edits.
merge_rules() {
    local i=0 file clean=0
    for file in "${rules[@]}"; do
        i=$((i + 1))
        [ -f "$file" ] || continue
        base_of "$file" > "$work/base"
        if ! git merge-file -p "$file" "$work/base" "$template" > "$work/$i.merged" 2>/dev/null; then
            echo "collision  $file: a template change touches lines you edited; merge it by hand"
            rm -f "$work/$i.merged"
            clean=1
        fi
    done
    return "$clean"
}

[ $# -ge 1 ] || usage
action=$1
shift
case $action in
status)
    answer=no pending=0 blocked=0
    if [ "${1:-}" = --exit-code ]; then answer=yes; shift; fi
    [ $# -eq 0 ] || usage
    echo "This checkout: $(git -C "$swe" rev-parse --abbrev-ref HEAD) at $(git -C "$swe" rev-parse --short HEAD)"
    if preview=$(bash "$swe/scripts/install_isolation.sh" 2>&1); then
        printf '%s\n' "$preview"
        if grep -q '^== ' <<<"$preview"; then pending=1; fi
    else
        printf '%s\n' "$preview"
        echo "install_isolation.sh stopped; see the lines above"
        blocked=1
    fi
    merge_rules || blocked=1
    i=0
    for file in "${rules[@]}"; do
        i=$((i + 1))
        if [ ! -f "$file" ]; then
            echo "absent     $file (install the filled-in template once by hand)"
        elif [ ! -f "$work/$i.merged" ]; then
            :
        elif cmp -s "$file" "$work/$i.merged"; then
            echo "unchanged  $file"
        else
            echo "would merge template changes into $file"
            pending=1
        fi
    done
    if [ ! -d "$HOME/.codex" ]; then
        :
    elif cmp -s "$codex_rules" "$swe/codex/default.rules"; then
        echo "unchanged  $codex_rules"
    else
        echo "would update $codex_rules"
        pending=1
    fi
    if [ ! -f "$hooks/pre-push" ]; then
        echo "absent     $hooks/pre-push (left alone)"
    elif [ -L "$hooks/pre-push" ]; then
        echo "linked     $hooks/pre-push follows the file it points to (left alone)"
    elif cmp -s "$hooks/pre-push" "$swe/.claude/scripts/pre-push" \
            && cmp -s "$hooks/tells_check.py" "$swe/.claude/scripts/tells_check.py"; then
        echo "unchanged  $hooks/pre-push"
    else
        echo "would update $hooks/pre-push"
        pending=1
    fi
    if [ -f "$HOME/.codex/AGENTS.md" ]; then
        size=$({ cat "$HOME/.codex/AGENTS.md" "$root/AGENTS.md" "$swe/AGENTS.md" 2>/dev/null || true; } | wc -c)
        limit=$({ sed -n 's/^project_doc_max_bytes *= *\([0-9]*\).*/\1/p' "$HOME/.codex/config.toml" 2>/dev/null || true; } | head -n 1)
        if [ "$size" -gt "${limit:-32768}" ]; then
            echo "warning    Codex instruction files total $size bytes, over its limit of ${limit:-32768}, and the rest is dropped silently; set project_doc_max_bytes in ~/.codex/config.toml"
        fi
    fi
    target="$(revert_target)"
    echo "Revert goes back to: ${target:-nothing, no apply is waiting to be reverted}"
    if [ "$answer" = yes ] && [ "$blocked" = 1 ]; then exit 2; fi
    if [ "$answer" = yes ] && [ "$pending" = 1 ]; then exit 1; fi
    ;;
apply)
    context=""
    if [ $# -gt 0 ]; then
        [ $# -eq 2 ] && [ "$1" = --context ] || usage
        context=$2
        [ -f "$context" ] || die "no context file $context"
        [ -d "$root/.lattice" ] || die "no board at $root/.lattice for --context; nothing was written"
    fi
    merge_rules || die "nothing was written"
    if [ -d "$HOME/.codex" ]; then
        if [ -L "$codex_rules" ] && [ ! -e "$codex_rules" ]; then die "$codex_rules is a link to nothing; nothing was written"; fi
        [ ! -e "$codex_rules" ] || [ -f "$codex_rules" ] || die "$codex_rules is not a file; nothing was written"
        [ ! -e "$(dirname "$codex_rules")" ] || [ -d "$(dirname "$codex_rules")" ] \
            || die "$(dirname "$codex_rules") is not a folder; nothing was written"
    fi
    bash "$swe/scripts/install_isolation.sh" > "$work/preview" 2>&1 \
        || { cat "$work/preview" >&2; die "install_isolation.sh would stop; nothing was written"; }
    snap="$store/$(date -u +%Y%m%dT%H%M%SZ)"
    [ ! -e "$snap" ] || die "snapshot $snap exists; wait a second and rerun"
    mkdir -p "$snap/files"
    chmod 700 "$store" "$snap"
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            mkdir -p "$snap/files$(dirname "$file")"
            cp -p "$file" "$snap/files$file"
            printf 'present\t%s\n' "$file"
        else
            printf 'absent\t%s\n' "$file"
        fi
    done > "$snap/manifest"
    before="$(cat "$marker" 2>/dev/null || true)"
    [ -n "$before" ] && [ -f "$store/$before/manifest" ] || basename "$snap" > "$marker"
    echo "saved      $snap"
    bash "$swe/scripts/install_isolation.sh" --apply
    i=0
    for file in "${rules[@]}"; do
        i=$((i + 1))
        if [ -f "$work/$i.merged" ] && ! cmp -s "$file" "$work/$i.merged"; then
            cat "$work/$i.merged" > "$file"
            echo "merged     $file"
        fi
    done
    if [ -d "$HOME/.codex" ] && ! cmp -s "$codex_rules" "$swe/codex/default.rules"; then
        mkdir -p "$(dirname "$codex_rules")"
        cp "$swe/codex/default.rules" "$codex_rules"
        echo "installed  $codex_rules"
    fi
    if [ -f "$hooks/pre-push" ] && [ ! -L "$hooks/pre-push" ]; then
        cp "$swe/.claude/scripts/pre-push" "$swe/.claude/scripts/tells_check.py" "$hooks/"
        chmod +x "$hooks/pre-push"
        echo "installed  $hooks/pre-push"
    fi
    if [ -n "$context" ]; then
        cp "$context" "$root/.lattice/context.md"
        echo "installed  $root/.lattice/context.md"
    fi
    echo
    echo "Restart every Claude Code and Codex session. To go back: $0 revert"
    ;;
revert)
    [ $# -le 1 ] || usage
    target="$(revert_target)"
    if [ $# -eq 0 ]; then
        snap="$target"
        [ -n "$snap" ] || die "nothing to revert: no apply since the last revert. Name a snapshot under $store to restore that one."
    else
        snap="$store/$(basename "$1")"
    fi
    [ -f "$snap/manifest" ] || die "no snapshot at $snap"
    while IFS=$'\t' read -r state file; do
        known "$file" || die "$snap/manifest names $file, which this script does not manage"
    done < "$snap/manifest"
    read -r -p "Put back the files saved in $snap? [y/N] " answer
    [ "$answer" = y ] || { echo "Nothing changed."; exit 1; }
    while IFS=$'\t' read -r state file; do
        saved="$snap/files$file"
        if [ "$state" = present ]; then
            if [ -f "$file" ] && cmp -s "$saved" "$file"; then
                echo "unchanged  $file"
            elif managed "$file"; then
                sudo install -m "$(stat -c %a "$saved")" -o root -g root "$saved" "$file"
                echo "restored   $file"
            else
                cp -p "$saved" "$file"
                echo "restored   $file"
            fi
        elif [ -e "$file" ]; then
            if managed "$file"; then sudo rm "$file"; else rm "$file"; fi
            echo "removed    $file"
        fi
    done < "$snap/manifest"
    [ "$snap" != "$target" ] || rm -f "$marker"
    echo
    echo "Restart every Claude Code and Codex session."
    ;;
*) usage ;;
esac
