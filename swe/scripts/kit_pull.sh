#!/usr/bin/env bash
# Move a project's kit clone to one signed release, after saying what the move
# changes. Run it yourself, from the top of the project:
#
#   bash .agent-alignment/swe/scripts/kit_pull.sh v1.2.0            that release
#   bash .agent-alignment/swe/scripts/kit_pull.sh latest            the newest release the kit lists
#   bash .agent-alignment/swe/scripts/kit_pull.sh --report latest   check and report; move nothing
#
# It works on ./.agent-alignment and nothing else, and never commits or pushes.
# It refuses, leaving the clone on its commit: a clone with local changes; a tag
# without an SSH signature by a key in ~/.config/agent-alignment/allowed_signers;
# a signed tag served under another name; and, for latest, a release that is
# not ahead of the clone. Run again with the same name, it changes nothing and
# says so. Its checks hold only where sessions cannot write the clone.
# LATTICE_ONBOARDING.md, "Updating the kit in a project", has the procedure.
#
# Exit 0: moved, already there, or reported. Exit 1: STOP, with the reason.
# Exit 64: wrong arguments.
set -euo pipefail

stop() { echo "STOP: $*" >&2; exit 1; }

# A release name: v and three numbers without leading zeros, such as v1.2.0.
number='(0|[123456789][0123456789]{0,8})'
version="^v$number\\.$number\\.$number\$"

# The checkout can replace this file, so Bash reads all of it before any runs.
main() {
    local report=no asked tag signers="$HOME/.config/agent-alignment/allowed_signers"
    local clone changes ignored url listed name release signed target
    if [ "${1:-}" = --report ]; then report=yes; shift; fi
    [ $# -eq 1 ] || { echo "usage: $0 [--report] <release>|latest" >&2; exit 64; }
    asked=$1 tag=$1
    [ "$tag" = latest ] || [[ $tag =~ $version ]] || stop "a release is named like v1.2.0, or is the word latest; not $tag"
    [ -s "$signers" ] || stop "no allowed signers file at $signers; nothing was fetched"
    # Git variables the terminal passes on could point Git at another repository.
    unset $(git rev-parse --local-env-vars)
    [ ! -L .agent-alignment ] && clone=$(cd ./.agent-alignment 2>/dev/null && pwd -P) \
        || stop "no .agent-alignment folder in $PWD; run this from the top of the project"
    [ "$(git -C "$clone" rev-parse --absolute-git-dir 2>/dev/null)" = "$clone/.git" ] \
        || stop "$clone is not a Git clone of its own; nothing was fetched"
    kit() { git -C "$clone" "$@"; }

    changes=$(kit status --porcelain --untracked-files=normal --ignored) \
        || stop "git status failed in $clone, so its state is unknown; nothing was fetched"
    ignored=$(grep '^!! ' <<< "$changes" || true)
    changes=$(grep -v '^!! ' <<< "$changes" || true)
    if [ -n "$changes" ]; then
        echo "changed  in $clone, the first 20 of $(grep -c '' <<< "$changes"):"
        head -n 20 <<< "$changes"
        stop "$clone has local changes, listed above; nothing was fetched"
    fi
    echo "now      $(kit describe --tags --exact-match --match 'v[0-9]*' HEAD 2>/dev/null || echo "not on a release") ($(kit rev-parse --short HEAD))"
    if [ -n "$ignored" ]; then
        echo "note     ignored files present, not part of a release; the first 20:"
        head -n 20 <<< "$ignored"
    fi

    url=$(kit remote get-url origin) || stop "$clone has no origin to fetch from"
    if [ "$tag" = latest ]; then
        listed=$(kit ls-remote --sort=-version:refname --tags --refs origin 'v*') \
            || stop "the releases of $url could not be listed; the clone is unchanged"
        while read -r _ name; do
            name=${name#refs/tags/}
            if [[ $name =~ $version ]]; then tag=$name; break; fi
        done <<< "$listed"
        [ "$tag" != latest ] || stop "$url lists no release; the clone is unchanged"
        echo "latest   $tag, the newest release $url lists"
    fi

    kit fetch -q --no-tags origin "refs/tags/$tag" \
        || stop "release $tag could not be fetched from $url; the clone is unchanged"
    release=$(kit rev-parse --verify FETCH_HEAD)
    # Only an SSH signature by a key in the allowed signers file passes: the
    # other kinds of signature Git knows are given a checker that always fails.
    signed=$(kit -c gpg.ssh.allowedSignersFile="$signers" -c gpg.program=false -c gpg.x509.program=false \
        verify-tag --format='%(tag)' "$release") \
        || stop "release $tag has no signature from a key in $signers; the clone is unchanged"
    [ "$signed" = "$tag" ] \
        || stop "the tag served as $tag was signed under the name $signed; the clone is unchanged"
    target=$(kit rev-parse "$release^{commit}")
    echo "release  $tag ($(kit rev-parse --short "$target")), signed by a key in $signers"
    # Kept, where the clone is on the release, so a later run can name it; nothing is decided from it.
    record() { [ "$report" = yes ] || kit update-ref "refs/tags/$tag" "$release"; }

    if [ "$(kit rev-parse HEAD)" = "$target" ]; then
        record
        echo "DONE: $clone was already at release $tag; nothing changed"
        return
    fi
    # A stale or hostile kit must not move the clone back, so latest only goes forward.
    [ "$asked" != latest ] || kit merge-base --is-ancestor HEAD "$target" \
        || stop "the newest release $url lists, $tag, is not ahead of this clone; the clone is unchanged. To move to it anyway, name it"
    echo "differs  from what the clone holds now, at most 20 files shown:"
    kit --no-pager diff --no-ext-diff --stat --stat-count=20 HEAD "$target"
    if [ "$report" = yes ]; then
        echo "DONE: report only; $clone was left as it was. Without --report this moves it to release $tag"
        return
    fi
    kit checkout -q --detach "$release" || stop "release $tag is signed but could not be checked out; Git says why above"
    record
    echo "DONE: $clone is now at release $tag ($(kit rev-parse --short "$target"))"
}
main "$@"
