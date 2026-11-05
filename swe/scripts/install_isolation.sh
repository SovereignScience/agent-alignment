#!/usr/bin/env bash
# Install the managed layer of this track on a Linux or WSL machine from this
# checkout. Run it yourself in a terminal; sessions cannot write these files.
#
#   swe/scripts/install_isolation.sh           show every change, write nothing
#   swe/scripts/install_isolation.sh --apply   back up each file, then install
#
# Files it installs:
#   /etc/claude-code/managed-settings.json            from .claude/managed-settings.example.json
#   /etc/claude-code/managed-settings.d/50-local.json from the local file below, if present
#   /etc/claude-code/hooks/                           guard_outward.py, tells_check.py, after_summary.sh,
#                                                     fetch_allow.txt (never fetch_allow.local.txt)
#   ~/.claude/settings.json                           drops rules the managed layer replaces
#   ~/.codex/config.toml                              adds the same read denials for Codex
#
# SWE_WORKSPACE is the folder that holds your checkouts (default ~/projects).
# SWE_MANAGED_LOCAL is this machine's own paths (default
# ~/.config/agent-alignment/managed-local.json): a production checkout to hide,
# extra toolchains to read, credential files. Start it from
# .claude/managed-local.example.json. It stays out of git.
set -euo pipefail

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${SWE_WORKSPACE:-$HOME/projects}"
local_file="${SWE_MANAGED_LOCAL:-$HOME/.config/agent-alignment/managed-local.json}"
etc=/etc/claude-code
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
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

# Managed settings: the reviewed example with the workspace root filled in.
text = pathlib.Path(swe, ".claude/managed-settings.example.json").read_text()
managed = json.loads(text.replace("~/projects", ws))
for key, value in managed.get("env", {}).items():
    if value.startswith("~/"):
        managed["env"][key] = home + value[1:]
(stage / "managed-settings.json").write_text(json.dumps(managed, indent=2) + "\n")

# Local drop-in: may only narrow the policy, plus re-allow reads it names.
local = {}
if os.path.exists(local_file):
    local = json.load(open(local_file))
    allowed = {("permissions", "deny"), ("sandbox", "filesystem", "denyRead"),
               ("sandbox", "filesystem", "denyWrite"), ("sandbox", "filesystem", "allowRead"),
               ("sandbox", "credentials", "files")}
    def walk(node, path=()):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, path + (k,))
        else:
            yield path, node
    for path, value in walk(local):
        if path not in allowed or not isinstance(value, list):
            sys.exit("local file %s: %s is not allowed there; it may hold only %s"
                     % (local_file, ".".join(path), ", ".join(".".join(a) for a in sorted(allowed))))
    for entry in local.get("sandbox", {}).get("credentials", {}).get("files", []):
        if entry.get("mode") != "deny":
            sys.exit("local file %s: credential entries must use mode deny" % local_file)
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
    for key in ("deny", "allow"):
        if key in perms:
            perms[key] = [r for r in perms[key] if r not in drop]
    # All of /tmp as a working directory lets the file tools write anywhere in it.
    if "/tmp" in perms.get("additionalDirectories", []):
        perms["additionalDirectories"] = ["/tmp/claude-%d" % os.getuid() if d == "/tmp" else d
                                          for d in perms["additionalDirectories"]]
    (stage / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")

# Codex: the snippet's read denials plus the local file's, added under the
# profile's filesystem table when missing.
codex = pathlib.Path(home, ".codex/config.toml")
if codex.exists():
    snippet = tomllib.loads(pathlib.Path(swe, "codex/config.snippet.toml").read_text())
    wanted = [p for p, v in snippet["permissions"]["workstation"]["filesystem"].items() if v == "deny"]
    wanted += local.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
    wanted += [e["path"] for e in local.get("sandbox", {}).get("credentials", {}).get("files", [])]
    current = codex.read_text()
    table = tomllib.loads(current).get("permissions", {}).get("workstation", {}).get("filesystem")
    header = re.compile(r"^\[permissions\.workstation\.filesystem\][ \t]*\n", re.MULTILINE)
    if table is None or len(header.findall(current)) != 1:
        print("codex: %s has no single [permissions.workstation.filesystem] table;"
              " add these lines to it yourself:" % codex)
        print("\n".join('"%s" = "deny"' % p for p in wanted))
    else:
        missing = [p for p in dict.fromkeys(wanted) if p not in table]
        lines = "".join('"%s" = "deny"\n' % p for p in missing)
        updated = header.sub(lambda m: m.group(0) + lines, current, count=1)
        tomllib.loads(updated)
        (stage / "config.toml").write_text(updated)
PY

cp "$swe/.claude/scripts/guard_outward.py" "$swe/.claude/scripts/tells_check.py" \
   "$swe/.claude/scripts/after_summary.sh" "$swe/.claude/scripts/fetch_allow.txt" "$stage/"
python3 -m py_compile "$stage/guard_outward.py" "$stage/tells_check.py"
rm -rf "$stage/__pycache__"

# target:staged-name:owner:mode
targets=(
    "$etc/managed-settings.json:managed-settings.json:root:0644"
    "$etc/managed-settings.d/50-local.json:50-local.json:root:0644"
    "$etc/hooks/guard_outward.py:guard_outward.py:root:0755"
    "$etc/hooks/tells_check.py:tells_check.py:root:0644"
    "$etc/hooks/after_summary.sh:after_summary.sh:root:0644"
    "$etc/hooks/fetch_allow.txt:fetch_allow.txt:root:0644"
    "$HOME/.claude/settings.json:settings.json:user:keep"
    "$HOME/.codex/config.toml:config.toml:user:keep"
)
changed=()
for t in "${targets[@]}"; do
    IFS=: read -r target name owner mode <<<"$t"
    [ -f "$stage/$name" ] || continue
    if [ -f "$target" ] && cmp -s "$target" "$stage/$name"; then
        echo "unchanged  $target"
        continue
    fi
    echo "== $target"
    if [ -f "$target" ] && [ "${name%.json}" != "$name" ]; then
        # Compare parsed JSON, so layout differences do not hide the real changes.
        diff -u --label "installed" --label "new" <(python3 -m json.tool "$target") \
            <(python3 -m json.tool "$stage/$name") || true
    elif [ -f "$target" ]; then
        diff -u --label "installed" --label "new" "$target" "$stage/$name" || true
    else
        diff -u --label "(no file yet)" --label "new" /dev/null "$stage/$name" || true
    fi
    changed+=("$t")
done

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

sudo install -d -m 0755 "$etc" "$etc/hooks" "$etc/managed-settings.d"
for t in "${changed[@]}"; do
    IFS=: read -r target name owner mode <<<"$t"
    if [ "$owner" = root ]; then
        [ -f "$target" ] && sudo cp -a "$target" "$target.$stamp.bak"
        sudo install -m "$mode" -o root -g root "$stage/$name" "$target"
    else
        cp -a "$target" "$target.$stamp.bak"
        cat "$stage/$name" > "$target"
    fi
    echo "installed  $target"
done
install -d -m 0700 "$HOME/.cache-agent"
echo
echo "Done. Restart every Claude Code and Codex session, then ask an agent to run"
echo "swe/scripts/check_isolation.sh in the sandbox."
