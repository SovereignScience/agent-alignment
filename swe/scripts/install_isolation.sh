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
# the rules it adds or removes, and env values in managed settings are masked.
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
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

python3 - "$swe" "$workspace" "$local_file" "$stage" <<'PY'
import json, os, pathlib, re, sys, tomllib

swe, workspace, local_file, stage = sys.argv[1:]
home = os.path.expanduser("~")
ws = "~/" + os.path.relpath(workspace, home) if workspace.startswith(home + "/") else workspace
stage = pathlib.Path(stage)
notes = []

def stop(message):
    sys.exit("install_isolation: " + message + "\nNothing was written.")

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

# Codex: the snippet's read denials plus the local file's, added to the
# workstation profile. A conflicting grant or an unexpected layout stops the run.
codex = pathlib.Path(home, ".codex/config.toml")
if codex.exists():
    snippet = tomllib.loads(pathlib.Path(swe, "codex/config.snippet.toml").read_text())
    wanted = [p for p, v in snippet["permissions"]["workstation"]["filesystem"].items() if v == "deny"]
    wanted += local.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
    wanted += [e["path"] for e in local.get("sandbox", {}).get("credentials", {}).get("files", [])]
    current = codex.read_text()
    try:
        config = tomllib.loads(current)
    except tomllib.TOMLDecodeError as error:
        stop("%s does not parse: %s" % (codex, error))
    if config.get("default_permissions") != "workstation":
        stop('%s must set default_permissions = "workstation" (see codex/config.snippet.toml)' % codex)
    table = config.get("permissions", {}).get("workstation", {}).get("filesystem")
    header = re.compile(r"^\[permissions\.workstation\.filesystem\][ \t]*\n", re.MULTILINE)
    if not isinstance(table, dict) or len(header.findall(current)) != 1:
        stop("%s needs exactly one [permissions.workstation.filesystem] table, written as a table "
             "header; add the profile from codex/config.snippet.toml first" % codex)
    conflicts = [p for p in dict.fromkeys(wanted) if p in table and table[p] != "deny"]
    if conflicts:
        stop("%s grants %s; change each to \"deny\" or remove it, then rerun"
             % (codex, ", ".join('"%s" = "%s"' % (p, table[p]) for p in conflicts)))
    missing = [p for p in dict.fromkeys(wanted) if p not in table]
    lines = "".join('"%s" = "deny"\n' % p for p in missing)
    updated = header.sub(lambda m: m.group(0) + lines, current, count=1)
    tomllib.loads(updated)
    (stage / "config.toml").write_text(updated)
    (stage / "config.toml.changes").write_text("".join("add %s\n" % line for line in lines.splitlines()))

(stage / "notes").write_text("\n".join(notes) + ("\n" if notes else ""))
PY

cp "$swe/.claude/scripts/guard_outward.py" "$swe/.claude/scripts/tells_check.py" \
   "$swe/.claude/scripts/after_summary.sh" "$swe/.claude/scripts/fetch_allow.txt" "$stage/"
cp "$swe/codex/requirements.toml" "$stage/requirements.toml"
python3 -m py_compile "$stage/guard_outward.py" "$stage/tells_check.py"
rm -rf "$stage/__pycache__"

# Managed settings with every env value masked, for display only.
masked() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
d["env"] = {k: "(set)" for k in d.get("env", {})}
print(json.dumps(d, indent=2))' "$1"
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
changed=()
for t in "${targets[@]}"; do
    IFS=: read -r target name owner mode display <<<"$t"
    [ -f "$stage/$name" ] || continue
    if [ -f "$target" ] && cmp -s "$target" "$stage/$name"; then
        echo "unchanged  $target"
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

if [ "${#changed[@]}" -eq 0 ]; then
    echo "Nothing to change."
    exit 0
fi
if [ "$apply" != yes ]; then
    echo
    echo "Nothing written. Review the changes above, then rerun with --apply."
    exit 0
fi
read -r -p "Install ${#changed[@]} file(s)? Each is backed up as <file>.$stamp.bak. [y/N] " answer
[ "$answer" = y ] || { echo "Nothing written."; exit 1; }

installed=()
report() {
    [ "${#installed[@]}" -gt 0 ] || return 0
    echo
    echo "Installed ${#installed[@]} of ${#changed[@]} file(s). To undo, run:"
    for t in "${installed[@]}"; do
        IFS=: read -r target _ owner _ _ <<<"$t"
        sudo_cmd=""; [ "$owner" = root ] && sudo_cmd="sudo "
        if [ -e "$target.$stamp.bak" ]; then
            echo "  ${sudo_cmd}cp -a '$target.$stamp.bak' '$target'"
        else
            echo "  ${sudo_cmd}rm '$target'"
        fi
    done
}
# shellcheck disable=SC2154  # status is assigned inside the trap text
trap 'status=$?; report; rm -rf "$stage"; [ "$status" -eq 0 ] || echo "Stopped part way; the files above are installed, the rest are not." >&2' EXIT

sudo install -d -m 0755 "$etc" "$etc/hooks" "$etc/managed-settings.d" "$codex_etc"
for t in "${changed[@]}"; do
    IFS=: read -r target name owner mode _ <<<"$t"
    if [ "$owner" = root ]; then
        [ -f "$target" ] && sudo cp -a "$target" "$target.$stamp.bak"
        sudo install -m "$mode" -o root -g root "$stage/$name" "$target"
    else
        cp -a "$target" "$target.$stamp.bak"
        cat "$stage/$name" > "$target"
    fi
    installed+=("$t")
    echo "installed  $target"
done
install -d -m 0700 "$HOME/.cache-agent" "$HOME/.config/agent-alignment"
sentinel="$HOME/.config/agent-alignment/sentinel"
[ -f "$sentinel" ] || ( umask 077; echo "agent-alignment sentinel: made-up content, not a secret" > "$sentinel" )
echo
echo "Done. Restart every Claude Code and Codex session, confirm Codex starts on the"
echo "workstation profile and refuses Full Access, then ask an agent to run"
echo "swe/scripts/check_isolation.sh in a fresh session of each client."
