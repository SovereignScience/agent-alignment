# Sourced by update_all.sh, board_update.sh and finish_batch.sh before they
# write to a repository.
#
#   git_elsewhere <work tree>
#
# The work tree is a physical path. Prints why Git could take a write there into
# another repository, and succeeds, when its .git holds a symbolic link (a single
# hook file aside, which the callers never write through), a file with another
# hard link (object files aside, which Git never rewrites), or Git finds its
# repository or work tree somewhere else. Fails, printing nothing, otherwise.
#
#   board_push <project top>
#
# Pushes main from the project's .lattice to its origin when the push address is
# the one the owner confirmed, kept as lattice-board.remote in the project's Git
# config. Any other address is shown and asked about on the terminal, never
# stdin; y records it and pushes. Fails, having pushed nothing, on any other
# answer, with no terminal, or when origin has several push addresses or one
# that carries a user or token, which it never prints.
git_environment_elsewhere() {
    local name configured status=0
    for name in "${!GIT_@}"; do
        case $name in
            GIT_DIR|GIT_COMMON_DIR|GIT_WORK_TREE|GIT_IMPLICIT_WORK_TREE|GIT_INDEX_FILE|\
            GIT_OBJECT_DIRECTORY|GIT_ALTERNATE_OBJECT_DIRECTORIES|GIT_GRAFT_FILE|\
            GIT_SHALLOW_FILE|GIT_REPLACE_REF_BASE|GIT_NO_REPLACE_OBJECTS|GIT_PREFIX|\
            GIT_NAMESPACE|GIT_QUARANTINE_PATH|GIT_CONFIG*|GIT_TRACE*)
                echo "$name is set; Git may use another repository or configuration"
                return 0 ;;
        esac
    done
    configured=$(GIT_TRACE2=0 GIT_TRACE2_EVENT=0 GIT_TRACE2_PERF=0 \
        git -C "${1:-$PWD}" config --name-only --get-regexp '^trace2\.(normal|perf|event)target$' 2>/dev/null) || status=$?
    case $status in
        0) echo "$configured is configured; Git tracing may write elsewhere" ;;
        1) return 1 ;;
        *) echo "Git tracing configuration could not be read" ;;
    esac
}

git_elsewhere() {
    local top=$1 git=$1/.git found
    found=$(find -P "$git" -path "$git/hooks/*" -prune -o -type l -print -quit \
        -o -type f -links +1 ! -path "$git/objects/*" -print -quit) \
        || { echo "$(basename "$top")/.git could not be read in full"; return 0; }
    if [ -n "$found" ]; then
        echo "${found#"$(dirname "$top")"/} is a link"
    elif found=$(git_environment_elsewhere "$top"); then
        echo "$found"
    elif [ "$(git -C "$top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" != "$git" ] \
            || [ "$(git -C "$top" rev-parse --show-toplevel 2>/dev/null)" != "$top" ]; then
        echo "Git finds the repository or work tree of $(basename "$top") elsewhere"
    else
        return 1
    fi
}

board_push() {
    local top=$1 address url scheme authority confirmed answer
    address=$(git -C "$top/.lattice" remote get-url --push --all origin) || return 1
    if [[ $address == *$'\n'* ]]; then
        echo "the board's origin has more than one push address"; return 1
    fi
    if [[ $address == *[[:cntrl:]]* ]]; then
        echo "the board's push address holds control characters; set it plainly"; return 1
    fi
    # A token rides in the user part: any user for http(s), a password for any other scheme,
    # including Git's <transport>::<address> form.
    url=${address#*::}
    if [[ $url == *://* ]]; then
        scheme=${url%%://*}; scheme=${scheme,,}; authority=${url#*://}; authority=${authority%%/*}
        if [[ $authority == *@* ]] && { [[ $scheme == http || $scheme == https ]] || [[ ${authority%@*} == *:* ]]; }; then
            echo "the board's push address carries a user or token; set it without one"; return 1
        fi
    fi
    confirmed=$(git -C "$top" config --get lattice-board.remote) || confirmed=""
    if [ "$address" != "$confirmed" ]; then
        echo "the board's pushes go to $address"
        echo "confirmed before: ${confirmed:-none}"
        printf 'Push the board to %s? [y/N] ' "$address" 2>/dev/null >/dev/tty \
            || { echo "no terminal to confirm it on; run this yourself at a terminal"; return 1; }
        read -r answer </dev/tty && [[ $answer == [yY] ]] || return 1
        git -C "$top" config lattice-board.remote "$address" || return 1
    fi
    git -C "$top/.lattice" push -q origin main
}
