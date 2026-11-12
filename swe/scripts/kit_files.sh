# Sourced by switch_rules.sh and update_all.sh: how a kit agent or slash
# command looks once installed outside this folder. The caller sets $swe to
# this kit's swe folder first.

kit_note="The kit's files that this names (the five protocols, CRAFT.md, and anything under scripts/ or tools/) are in $swe, whichever project you are in."

# A kit agent or command as it is installed: the note follows its front matter.
render() {
    awk -v note="$kit_note" '
        NR == 1 && $0 == "---" { print; front = 1; next }
        front && $0 == "---" { print; print ""; print note; front = 0; next }
        NR == 1 { print note; print "" }
        { print }' "$1"
}
