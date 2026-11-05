#!/usr/bin/env bash
# Install the managed layer of this track on a Linux or WSL machine from a
# reviewed checkout. Run it yourself in a terminal; sessions cannot write these
# files.
#
#   swe/scripts/install_isolation.sh           show every change, write nothing
#   swe/scripts/install_isolation.sh --apply   back up each file, then install
#
# Files it installs:
#   /etc/claude-code/managed-settings.json            from .claude/managed-settings.example.json
#   /etc/claude-code/managed-settings.d/50-local.json from the local file below, if present
#   /etc/claude-code/hooks/                           guard_outward.py, tells_check.py, after_summary.sh,
#                                                     fetch_allow.txt (never fetch_allow.local.txt)
#   /etc/codex/requirements.toml                      from codex/requirements.toml
#   ~/.claude/settings.json                           drops rules the managed layer replaces
#   ~/.codex/config.toml                              adds the profile's read denials
#   ~/.config/agent-alignment/sentinel                made-up content for check_isolation.sh
#
# SWE_WORKSPACE is the folder that holds your checkouts (default ~/projects).
# SWE_MANAGED_LOCAL is this machine's own paths (default
# ~/.config/agent-alignment/managed-local.json): a production checkout to hide,
# extra toolchains to read, credential files. Start it from
# .claude/managed-local.example.json. It stays out of git.
# SWE_ETC and SWE_CODEX_ETC replace /etc/claude-code and /etc/codex, for tests.
#
# The preview never prints a setting's value: settings files are summarised by
# the rules it adds or removes, and managed settings are shown with every text
# value outside permissions, sandbox and hook matchers masked.
#
# It stops, writing nothing, when a managed directory is a symlink, is not
# owned by root or is writable by group or others; when a target is a symlink
# or not a regular file; when /etc/codex/requirements.toml already holds other
# content; or when the Codex profile is missing, extends another profile, turns
# network on, adds workspace roots, grants anything but denials or scans globs
# less deeply than the snippet. Without ~/.codex it leaves the Codex profile and
# /etc/codex alone. A managed file with the right content but the wrong owner or
# mode is reinstalled.
set -euo pipefail

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${SWE_WORKSPACE:-$HOME/projects}"
local_file="${SWE_MANAGED_LOCAL:-$HOME/.config/agent-alignment/managed-local.json}"
etc="${SWE_ETC:-/etc/claude-code}"
codex_etc="${SWE_CODEX_ETC:-/etc/codex}"
stamp="$(date -u +%Y%m%dT%H%M%S.%NZ)-$$"
apply=no
case "${1:-}" in
    --apply) apply=yes ;;
    "") ;;
    *) echo "usage: $0 [--apply]" >&2; exit 64 ;;
esac
[ -d "$workspace" ] || { echo "SWE_WORKSPACE $workspace does not exist" >&2; exit 1; }
test_dirs=no
[ -z "${SWE_ETC:-}${SWE_CODEX_ETC:-}" ] || test_dirs=yes
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

python3 - "$swe" "$workspace" "$local_file" "$stage" "$etc" "$codex_etc" "$test_dirs" <<'PY'
import json, os, pathlib, re, shutil, stat, sys, tomllib

swe, workspace, local_file, stage, etc, codex_etc, test_dirs = sys.argv[1:]
home = os.path.expanduser("~")
ws = "~/" + os.path.relpath(workspace, home) if workspace.startswith(home + "/") else workspace
stage = pathlib.Path(stage)
notes = []

def stop(message):
    sys.exit("install_isolation: " + message + "\nNothing was written.")

# Managed directories, from the one above each managed root down, must be real
# directories owned by root and closed to group and others; otherwise a user
# could swap the root-owned hooks inside. With SWE_ETC or SWE_CODEX_ETC set,
# for tests, directories you own also pass the owner check.
owners = {0, os.getuid()} if test_dirs == "yes" else {0}
def managed_dir(path):
    if not os.path.lexists(path):
        return False
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        stop("%s is a symlink; managed files must sit in real directories" % path)
    if not stat.S_ISDIR(st.st_mode):
        stop("%s is not a directory" % path)
    if st.st_uid not in owners:
        stop("%s is owned by uid %d; managed directories must be owned by root" % (path, st.st_uid))
    if st.st_mode & 0o022:
        stop("%s is writable by group or others" % path)
    return True
for top, subs in ((etc, ("hooks", "managed-settings.d")), (codex_etc, ())):
    top = os.path.normpath(top)
    if managed_dir(os.path.dirname(top)) and managed_dir(top):
        for sub in subs:
            managed_dir(os.path.join(top, sub))

# Managed settings: the reviewed example with the workspace root filled in.
text = pathlib.Path(swe, ".claude/managed-settings.example.json").read_text()
managed = json.loads(text.replace("~/projects", ws))
for key, value in managed.get("env", {}).items():
    if value.startswith("~/"):
        managed["env"][key] = home + value[1:]
(stage / "managed-settings.json").write_text(json.dumps(managed, indent=2) + "\n")

# Local drop-in: it may only add denials and read paths, as lists of
# non-empty strings, plus credential entries of exactly {path, mode: deny}.
LISTS = {("permissions", "deny"), ("sandbox", "filesystem", "denyRead"),
         ("sandbox", "filesystem", "denyWrite"), ("sandbox", "filesystem", "allowRead")}
CREDS = ("sandbox", "credentials", "files")
local = {}
if os.path.exists(local_file):
    try:
        local = json.load(open(local_file))
    except ValueError as error:
        stop("local file %s is not JSON: %s" % (local_file, error))
    def walk(node, path=()):
        if isinstance(node, dict) and path not in LISTS and path != CREDS:
            if not node:
                stop("local file %s: %s is an empty object" % (local_file, ".".join(path) or "the top level"))
            for k, v in node.items():
                yield from walk(v, path + (k,))
        else:
            yield path, node
    for path, value in walk(local):
        if path in LISTS:
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                stop("local file %s: %s must be a list of non-empty strings" % (local_file, ".".join(path)))
        elif path == CREDS:
            if not isinstance(value, list) or not all(
                    isinstance(e, dict) and set(e) == {"path", "mode"} and isinstance(e["path"], str)
                    and e["path"].strip() and e["mode"] == "deny" for e in value):
                stop("local file %s: %s entries must be exactly {\"path\": \"...\", \"mode\": \"deny\"}"
                     % (local_file, ".".join(CREDS)))
        else:
            stop("local file %s: %s is not allowed; it may hold only %s"
                 % (local_file, ".".join(path), ", ".join(".".join(p) for p in sorted(LISTS | {CREDS}))))
    (stage / "50-local.json").write_text(json.dumps(local, indent=2) + "\n")

# User settings: drop name-pattern reads (they hide library files such as
# PyYAML's tokens.py and miss the home directory, which the managed default-deny
# read covers), the Ansible denials the guard replaces, and home-wide read allows.
user = pathlib.Path(home, ".claude/settings.json")
codex_dir = pathlib.Path(home, ".codex")
codex = codex_dir / "config.toml"
for path in (user, codex):
    if path.is_symlink():
        stop("%s is a symlink; make it a regular file, then rerun" % path)
if user.exists():
    settings = json.loads(user.read_text())
    perms = settings.get("permissions", {})
    drop = {"Read(**/*token*)", "Read(**/*secret*)", "Read(**/*credentials*)", "Read(**/*api_key*)",
            "Read(**/*apikey*)", "Read(**/*.crt)", "Read(**/known_hosts)",
            "Bash(ansible-playbook *)", "Bash(ansible *)",
            "Read(//%s/**)" % home.lstrip("/"), "Read(~/**)"}
    changes = []
    for key in ("deny", "allow"):
        removed = [r for r in perms.get(key, []) if r in drop]
        changes += ["remove permissions.%s %s" % (key, r) for r in removed]
        if removed:
            perms[key] = [r for r in perms[key] if r not in drop]
    dirs = perms.get("additionalDirectories", [])
    if "/tmp" in dirs:
        new = "/tmp/claude-%d" % os.getuid()
        perms["additionalDirectories"] = [new if d == "/tmp" else d for d in dirs]
        changes.append("replace permissions.additionalDirectories /tmp with %s" % new)
    for d in perms.get("additionalDirectories", []):
        real = os.path.realpath(os.path.expanduser(d))
        if real in (home, "/") or workspace == real or workspace.startswith(real.rstrip("/") + "/"):
            notes.append("warning: ~/.claude/settings.json additionalDirectories %s holds the whole "
                         "workspace, so the file tools may write every checkout under it" % d)
    (stage / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    (stage / "settings.json.changes").write_text("\n".join(changes) + ("\n" if changes else ""))

# Codex: the snippet's read denials, at the top level and for workspace roots,
# plus the local file's, added to the workstation profile. A profile that does
# more than the snippet's, or an unexpected layout, stops the run. The admin
# requirements that allow only this profile are staged only alongside it.
if codex_dir.exists() and not codex.exists():
    stop("%s is missing; add the profile from codex/config.snippet.toml first" % codex)
if not codex_dir.exists():
    notes.append("note: no ~/.codex, so the Codex profile and %s were left alone" % codex_etc)
if codex.exists():
    snippet = tomllib.loads(pathlib.Path(swe, "codex/config.snippet.toml").read_text())
    base = snippet["permissions"]["workstation"]["extends"]
    snippet_fs = snippet["permissions"]["workstation"]["filesystem"]
    ROOTS = ":workspace_roots"
    wanted = [p for p, v in snippet_fs.items() if v == "deny"]
    wanted += local.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
    wanted += [e["path"] for e in local.get("sandbox", {}).get("credentials", {}).get("files", [])]
    wanted = list(dict.fromkeys(wanted))
    wanted_roots = [p for p, v in snippet_fs[ROOTS].items() if v == "deny"]
    current = codex.read_text()
    try:
        config = tomllib.loads(current)
    except tomllib.TOMLDecodeError as error:
        stop("%s does not parse: %s" % (codex, error))
    if config.get("default_permissions") != "workstation":
        stop('%s must set default_permissions = "workstation" (see codex/config.snippet.toml)' % codex)
    profile = config.get("permissions", {}).get("workstation", {})
    table = profile.get("filesystem")
    header = re.compile(r"^\[permissions\.workstation\.filesystem\][ \t]*\n", re.MULTILINE)
    if not isinstance(table, dict) or len(header.findall(current)) != 1:
        stop("%s needs exactly one [permissions.workstation.filesystem] table, written as a table "
             "header; add the profile from codex/config.snippet.toml first" % codex)
    if profile.get("extends") != base:
        stop('%s: [permissions.workstation] must set extends = "%s", as codex/config.snippet.toml does'
             % (codex, base))
    if profile.get("network", {}).get("enabled"):
        stop("%s: the workstation profile turns command networking on; this track runs Codex "
             "commands without network" % codex)
    if profile.get("workspace_roots"):
        stop("%s: [permissions.workstation.workspace_roots] adds workspace roots; this track uses "
             "only the session's own workspace, so remove them, then rerun" % codex)
    def grants(node, path=()):
        for key, value in node.items():
            if isinstance(value, dict):
                yield from grants(value, path + (key,))
            elif isinstance(value, str) and value != "deny":
                yield ".".join(json.dumps(p) for p in path + (key,)) + " = " + json.dumps(value)
    granted = list(grants(table))
    if granted:
        stop("%s grants %s; the workstation profile may only add denials, so change each to "
             "\"deny\" or remove it, then rerun" % (codex, ", ".join(granted)))
    roots = table.get(ROOTS)
    roots_header = re.compile(r'^\[permissions\.workstation\.filesystem\.":workspace_roots"\][ \t]*\n',
                              re.MULTILINE)
    if roots is not None and (not isinstance(roots, dict) or len(roots_header.findall(current)) != 1):
        stop('%s: write [permissions.workstation.filesystem.":workspace_roots"] once, as a table '
             "header, then rerun" % codex)
    line = lambda p: '%s = "deny"\n' % json.dumps(p)
    missing = [p for p in wanted if p not in table]
    missing_roots = [p for p in wanted_roots if p not in (roots or {})]
    depth = snippet_fs["glob_scan_max_depth"]
    have = table.get("glob_scan_max_depth")
    if have is not None and (type(have) is not int or have < depth):
        stop("%s: glob_scan_max_depth is %r; the workspace-root denials need a whole number of at "
             "least %d, as codex/config.snippet.toml sets" % (codex, have, depth))
    add_depth = "" if have is not None else "glob_scan_max_depth = %d\n" % depth
    updated = header.sub(lambda m: m.group(0) + add_depth + "".join(map(line, missing)), current, count=1)
    if missing_roots and roots is None:
        updated = (updated.rstrip("\n") + '\n\n[permissions.workstation.filesystem.":workspace_roots"]\n'
                   + "".join(map(line, missing_roots)))
    elif missing_roots:
        updated = roots_header.sub(lambda m: m.group(0) + "".join(map(line, missing_roots)), updated, count=1)
    try:
        result = tomllib.loads(updated)["permissions"]["workstation"]["filesystem"]
    except (tomllib.TOMLDecodeError, KeyError) as error:
        stop("%s: adding the denials would break the file (%s); add them by hand from "
             "codex/config.snippet.toml" % (codex, error))
    scan = result.get("glob_scan_max_depth")
    if any(result.get(p) != "deny" for p in wanted) or \
            any(result.get(ROOTS, {}).get(p) != "deny" for p in wanted_roots) or \
            type(scan) is not int or scan < depth:
        stop("%s: the denials did not land where expected; add them by hand from "
             "codex/config.snippet.toml" % codex)
    (stage / "config.toml").write_text(updated)
    (stage / "config.toml.changes").write_text(
        ("add " + add_depth if add_depth else "")
        + "".join("add %s" % line(p) for p in missing)
        + "".join('add [":workspace_roots"] %s' % line(p) for p in missing_roots))
    shutil.copy(pathlib.Path(swe, "codex/requirements.toml"), stage / "requirements.toml")

(stage / "notes").write_text("\n".join(notes) + ("\n" if notes else ""))
PY

cp "$swe/.claude/scripts/guard_outward.py" "$swe/.claude/scripts/tells_check.py" \
   "$swe/.claude/scripts/after_summary.sh" "$swe/.claude/scripts/fetch_allow.txt" "$stage/"
python3 -m py_compile "$stage/guard_outward.py" "$stage/tells_check.py"
rm -rf "$stage/__pycache__"

# Managed settings for display only: text values outside permissions, sandbox
# and hook matchers, such as env, helpers and headers, are masked.
masked() {
    python3 -c 'import json, sys
def mask(node, path=()):
    if isinstance(node, dict):
        return {k: mask(v, path + (k,)) for k, v in node.items()}
    if isinstance(node, list):
        return [mask(v, path) for v in node]
    if isinstance(node, str) and path[:1] not in (("permissions",), ("sandbox",)) and path[-1:] != ("matcher",):
        return "(set)"
    return node
print(json.dumps(mask(json.load(open(sys.argv[1]))), indent=2))' "$1"
}

# target:staged-name:owner:mode:display
targets=(
    "$etc/managed-settings.json:managed-settings.json:root:0644:json"
    "$etc/managed-settings.d/50-local.json:50-local.json:root:0644:json"
    "$etc/hooks/guard_outward.py:guard_outward.py:root:0755:diff"
    "$etc/hooks/tells_check.py:tells_check.py:root:0644:diff"
    "$etc/hooks/after_summary.sh:after_summary.sh:root:0644:diff"
    "$etc/hooks/fetch_allow.txt:fetch_allow.txt:root:0644:diff"
    "$codex_etc/requirements.toml:requirements.toml:root:0644:diff"
    "$HOME/.claude/settings.json:settings.json:user:keep:summary"
    "$HOME/.codex/config.toml:config.toml:user:keep:summary"
)
for t in "${targets[@]}"; do
    IFS=: read -r target _ _ _ _ <<<"$t"
    if [ -L "$target" ] || { [ -e "$target" ] && [ ! -f "$target" ]; }; then
        echo "install_isolation: $target is a symlink or not a regular file; make it a regular file, then rerun" >&2
        echo "Nothing was written." >&2
        exit 1
    fi
done
if [ -f "$stage/requirements.toml" ] && [ -f "$codex_etc/requirements.toml" ] \
        && ! cmp -s "$codex_etc/requirements.toml" "$stage/requirements.toml"; then
    echo "install_isolation: $codex_etc/requirements.toml already holds other policy. Compare it with" >&2
    echo "codex/requirements.toml, merge the two by hand or move it aside, then rerun." >&2
    echo "Nothing was written." >&2
    exit 1
fi

# A managed file is unchanged only with the same bytes, root as owner (or you,
# in tests) and the mode it is installed with; otherwise it is reinstalled.
owners=(0)
[ "$test_dirs" = no ] || owners+=("$(id -u)")
managed_meta() {
    local uid perm u
    read -r uid perm < <(stat -c '%u %a' "$1")
    [ "$perm" = "${2#0}" ] || return 1
    for u in "${owners[@]}"; do [ "$uid" = "$u" ] && return 0; done
    return 1
}

changed=()
for t in "${targets[@]}"; do
    IFS=: read -r target name owner mode display <<<"$t"
    [ -f "$stage/$name" ] || continue
    if [ -f "$target" ] && cmp -s "$target" "$stage/$name"; then
        if [ "$owner" != root ] || managed_meta "$target" "$mode"; then
            echo "unchanged  $target"
            continue
        fi
        echo "== $target"
        echo "same content, but $(stat -c 'owner uid %u, mode %a' "$target"); reinstall as root with mode ${mode#0}"
        changed+=("$t")
        continue
    fi
    echo "== $target"
    case "$display" in
        summary) cat "$stage/$name.changes" ;;
        json)
            if [ -f "$target" ]; then
                diff -u --label installed --label new <(masked "$target") <(masked "$stage/$name") || true
            else
                diff -u --label "(no file yet)" --label new /dev/null <(masked "$stage/$name") || true
            fi ;;
        diff)
            if [ -f "$target" ]; then
                diff -u --label installed --label new "$target" "$stage/$name" || true
            else
                diff -u --label "(no file yet)" --label new /dev/null "$stage/$name" || true
            fi ;;
    esac
    changed+=("$t")
done
if [ ! -f "$local_file" ] && [ -f "$etc/managed-settings.d/50-local.json" ]; then
    echo "retained   $etc/managed-settings.d/50-local.json (no local file given; this run leaves it as it is)"
fi
cat "$stage/notes"

sentinel="$HOME/.config/agent-alignment/sentinel"
sentinel_text="agent-alignment sentinel: made-up content, not a secret"
sentinel_ok() { [ -f "$sentinel" ] && [ ! -L "$sentinel" ] && grep -qxF "$sentinel_text" "$sentinel"; }
prereq=()
[ -d "$HOME/.cache-agent" ] || prereq+=("$HOME/.cache-agent")
sentinel_ok || prereq+=("$sentinel")
for p in "${prereq[@]}"; do echo "write      $p"; done

if [ "${#changed[@]}" -eq 0 ] && [ "${#prereq[@]}" -eq 0 ]; then
    echo "Nothing to change."
    exit 0
fi
if [ "$apply" != yes ]; then
    echo
    echo "Nothing written. Review the changes above, then rerun with --apply."
    exit 0
fi
if [ "${#changed[@]}" -gt 0 ]; then
    read -r -p "Install ${#changed[@]} file(s)? Each is backed up as <file>.$stamp.bak. [y/N] " answer
    [ "$answer" = y ] || { echo "Nothing written."; exit 1; }
fi

installed=()
current=""
report() {
    if [ -n "$current" ]; then
        echo
        echo "Stopped while installing $current; it may be unchanged or partly written."
        [ -e "$current.$stamp.bak" ] && echo "Its earlier content is in $current.$stamp.bak."
    fi
    [ "${#installed[@]}" -gt 0 ] || return 0
    echo
    echo "Installed ${#installed[@]} of ${#changed[@]} file(s). To undo, run:"
    for t in "${installed[@]}"; do
        IFS=: read -r target _ owner _ _ <<<"$t"
        sudo_cmd=""; [ "$owner" = root ] && sudo_cmd="sudo "
        if [ -e "$target.$stamp.bak" ]; then
            printf '  %scp -a %q %q\n' "$sudo_cmd" "$target.$stamp.bak" "$target"
        else
            printf '  %srm %q\n' "$sudo_cmd" "$target"
        fi
    done
}
# shellcheck disable=SC2154  # status is assigned inside the trap text
trap 'status=$?; report; rm -rf "$stage"; [ "$status" -eq 0 ] || echo "Stopped part way; the lines above say what changed." >&2' EXIT

if [ "${#changed[@]}" -gt 0 ]; then
    dirs=("$etc" "$etc/hooks" "$etc/managed-settings.d")
    [ -f "$stage/requirements.toml" ] && dirs+=("$codex_etc")
    sudo install -d -m 0755 "${dirs[@]}"
fi
for t in "${changed[@]}"; do
    IFS=: read -r target name owner mode _ <<<"$t"
    current="$target"
    if [ "$owner" = root ]; then
        if [ -f "$target" ]; then sudo cp -a "$target" "$target.$stamp.bak"; fi
        sudo install -m "$mode" -o root -g root "$stage/$name" "$target"
    else
        cp -a "$target" "$target.$stamp.bak"
        cp -p "$target" "$target.$stamp.new"
        cat "$stage/$name" > "$target.$stamp.new"
        mv -f "$target.$stamp.new" "$target"
    fi
    installed+=("$t")
    current=""
    echo "installed  $target"
done
install -d -m 0700 "$HOME/.cache-agent" "$HOME/.config/agent-alignment"
sentinel_ok || { rm -f "$sentinel"; ( umask 077; echo "$sentinel_text" > "$sentinel" ); }
echo
echo "Done. Restart every Claude Code and Codex session, confirm Codex starts on the"
echo "workstation profile and refuses Full Access, then ask an agent to run"
echo "swe/scripts/check_isolation.sh --client claude, or --client codex, in a fresh"
echo "session of each client."
