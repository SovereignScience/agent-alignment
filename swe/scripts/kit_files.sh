# Sourced by switch_rules.sh, for how a kit agent or slash command looks once
# installed outside this folder, and by both scripts for the kit's Git hooks
# and how they are told from another tool's. update_all.sh and
# install_isolation.sh also take the owner's skip list from here. The caller
# sets $swe to this kit's swe folder first.

# The workspace folders the owner leaves out of every kit script, one name a
# line. read_skip adds them to the caller's skip array, and fails when there is
# no such file; an empty file leaves out nothing.
skip_file="$HOME/.config/agent-alignment/skip"
read_skip() {
    local line
    [ -f "$skip_file" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line#"${line%%[![:space:]]*}"} && line=${line%"${line##*[![:space:]]}"} && line=${line%/}
        [ -z "$line" ] || skip+=("$line")
    done < "$skip_file"
}

kit_mark="The kit's files that this names"
kit_note="$kit_mark (the five protocols, CRAFT.md, ADR_TEMPLATE.md, and anything under scripts/ or tools/) are in $swe, whichever project you are in; where the sandbox hides that folder, read them in .agent-alignment/swe at the top of the project's main checkout, and still name $swe in any command for the owner."
# The first line of the kit's push check, which tells it from another tool's hook.
kit_hook_mark="pre-push: show what is about to leave this machine"
# The kit's Git hooks and the files they import, copied together into a
# repository's hooks folder from $swe/.claude/scripts.
kit_hooks=(pre-push pre-commit commit-msg tells_check.py privacy_check.py)
kit_privacy_mark="the kit's privacy check"

# Another tool's pre-commit or commit-msg, or a link in its place, which the
# kit leaves alone.
foreign_hook() {
    case ${1##*/} in pre-commit | commit-msg) ;; *) return 1 ;; esac
    [ -L "$1" ] || { [ -e "$1" ] && ! grep -qF "$kit_privacy_mark" "$1"; }
}

# A kit agent or command as it is installed: the note follows its front matter.
render() {
    awk -v note="$kit_note" '
        NR == 1 && $0 == "---" { print; front = 1; next }
        front && $0 == "---" { print; print ""; print note; front = 0; next }
        NR == 1 { print note; print "" }
        { print }' "$1"
}
