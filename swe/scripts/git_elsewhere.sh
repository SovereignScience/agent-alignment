# Sourced by update_all.sh and board_update.sh before their first Git command.
# Sourcing it clears the Git variables that would point any repository's index,
# objects, work tree or config somewhere else (git rev-parse --local-env-vars).
#
#   git_elsewhere <work tree>
#
# The work tree is a physical path. Prints why Git could take a write there into
# another repository, and succeeds, when its .git holds a symbolic link (a single
# hook file aside, which the callers never write through), a file with another
# hard link (object files aside, which Git never rewrites), or Git finds its
# repository or work tree somewhere else. Fails, printing nothing, otherwise.
unset $(git rev-parse --local-env-vars)

git_elsewhere() {
    local top=$1 git=$1/.git found
    found=$(find -P "$git" -path "$git/hooks/*" -prune -o -type l -print -quit \
        -o -type f -links +1 ! -path "$git/objects/*" -print -quit) \
        || { echo "$(basename "$top")/.git could not be read in full"; return 0; }
    if [ -n "$found" ]; then
        echo "${found#"$(dirname "$top")"/} is a link"
    elif [ "$(git -C "$top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" != "$git" ] \
            || [ "$(git -C "$top" rev-parse --show-toplevel 2>/dev/null)" != "$top" ]; then
        echo "Git finds the repository or work tree of $(basename "$top") elsewhere"
    else
        return 1
    fi
}
