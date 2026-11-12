# Sourced by switch_rules.sh and update_all.sh: how a kit agent or slash
# command looks once installed outside this folder. The caller sets $swe to
# this kit's swe folder first.

kit_mark="The kit's files that this names"
kit_note="$kit_mark (the five protocols, CRAFT.md, ADR_TEMPLATE.md, and anything under scripts/ or tools/) are in $swe, whichever project you are in."
# The first line of the kit's push check, which tells it from another tool's hook.
kit_hook_mark="pre-push: show what is about to leave this machine"

# A kit agent or command as it is installed: the note follows its front matter.
render() {
    awk -v note="$kit_note" '
        NR == 1 && $0 == "---" { print; front = 1; next }
        front && $0 == "---" { print; print ""; print note; front = 0; next }
        NR == 1 { print note; print "" }
        { print }' "$1"
}
