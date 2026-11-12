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
#   /etc/codex/requirements.toml                      the Codex profile, built from codex/config.snippet.toml
#   ~/.claude/settings.json                           drops rules the managed layer replaces
#   ~/.codex/config.toml                              default_permissions set to that profile
#   ~/.config/agent-alignment/sentinel                made-up content for check_isolation.sh
#
# SWE_WORKSPACE is the folder that holds your checkouts (default: the folder
# this kit's main checkout is in).
# SWE_MANAGED_LOCAL is this machine's own paths (default
# ~/.config/agent-alignment/managed-local.json): a production checkout to hide,
# credential files. Start it from
# .claude/managed-local.example.json. It stays out of git.
# SWE_ETC and SWE_CODEX_ETC replace /etc/claude-code and /etc/codex, for tests.
#
# The preview never prints a setting's value: settings files are summarised by
# the rules it adds or removes, and managed settings are shown with every text
# value outside permissions, sandbox and hook matchers masked.
#
# It stops, writing nothing, when a managed directory is a symlink, is not
# owned by root or is writable by group or others; when a target is a symlink
# or not a regular file; when /etc/codex/requirements.toml holds policy this
# script did not write; when the local file re-opens paths; or when
# ~/.codex/config.toml is missing, defines the admin profile itself or picks
# another default. Without ~/.codex it leaves Codex and /etc/codex alone. A
# managed file with the right content but the wrong owner or mode is
# reinstalled. --apply also stops when this checkout's HEAD does not contain
# main, or the fetched upstream of main when it has one, so an older checkout
# cannot put back older rules.
set -euo pipefail

swe="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${SWE_WORKSPACE:-$(dirname "$(dirname "$(git -C "$swe" rev-parse --path-format=absolute --git-common-dir)")")}"
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
if [ "$apply" = yes ]; then
    upstream=$(git -C "$swe" rev-parse --abbrev-ref 'main@{upstream}' 2>/dev/null || true)
    for ref in main ${upstream:+"$upstream"}; do
        if ! git -C "$swe" merge-base --is-ancestor "$ref" HEAD; then
            echo "install_isolation: this checkout's HEAD does not contain $ref, so it could install older rules." >&2
            echo "Bring it up to date with $ref, or run this from an up-to-date main checkout." >&2
            echo "Nothing was written." >&2
            exit 1
        fi
    done
fi
[ -d "$workspace" ] || { echo "SWE_WORKSPACE $workspace does not exist" >&2; exit 1; }
test_dirs=no
[ -z "${SWE_ETC:-}${SWE_CODEX_ETC:-}" ] || test_dirs=yes
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

/usr/bin/python3 -I - "$swe" "$workspace" "$local_file" "$stage" "$etc" "$codex_etc" "$test_dirs" <<'PY'
import copy, json, os, pathlib, re, stat, sys, tomllib

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

# Local drop-in: it may only add denials, as lists of non-empty strings, plus
# credential entries of exactly {path, mode: deny}. allowRead is refused: on
# Linux, re-opened paths leave the working directory read-only and the sandbox
# cannot start.
LISTS = {("permissions", "deny"), ("sandbox", "filesystem", "denyRead"),
         ("sandbox", "filesystem", "denyWrite")}
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
            "Read(**/credentials)", "Read(**/*apikey*)", "Read(**/*.crt)", "Read(**/known_hosts)",
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

# Codex accepts an allowlist only of profiles defined in the requirements file,
# so the snippet's [permissions.workstation] body, plus the local file's
# denials, becomes the admin profile there: the default and the only profile
# allowed. Codex's sandbox cannot mask a symlink or a path that does not exist,
# so a symlinked denial is replaced by its target (or left out when the target
# is already denied or missing), and missing paths and paths inside a denied
# folder are left out. ~/.codex/config.toml only gets its default pointed at
# the admin profile.
PROFILE = "alignment_workstation"
MARK = "# Admin-enforced Codex requirements. Only the profile defined here may run,"
if codex_dir.exists() and not codex.exists():
    stop("%s is missing; create it with the settings in codex/config.snippet.toml first" % codex)
if not codex_dir.exists():
    notes.append("note: no ~/.codex, so Codex and %s were left alone" % codex_etc)
if codex.exists():
    snippet = tomllib.loads(pathlib.Path(swe, "codex/config.snippet.toml").read_text())
    body = snippet["permissions"]["workstation"]
    snippet_fs = body["filesystem"]
    ROOTS = ":workspace_roots"
    special = {k: v for k, v in snippet_fs.items() if k.startswith(":") and k != ROOTS}
    wanted = [p for p, v in snippet_fs.items() if v == "deny" and not p.startswith(":")]
    wanted += local.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
    wanted += [e["path"] for e in local.get("sandbox", {}).get("credentials", {}).get("files", [])]
    wanted = list(dict.fromkeys(wanted))
    ex = os.path.expanduser
    folders = [ex(p) for p in wanted if os.path.isdir(ex(p)) and not os.path.islink(ex(p))]
    def covered(path):
        return any(path == d or path.startswith(d.rstrip("/") + "/") for d in folders)
    denies, skipped = [], []
    for p in wanted:
        q = ex(p)
        if os.path.islink(q):
            target = os.path.realpath(q)
            if covered(target):
                skipped.append("%s (links into a denied folder)" % p)
            elif os.path.exists(target):
                denies.append(target)
            else:
                skipped.append("%s (links to a missing path)" % p)
        elif not os.path.lexists(q):
            skipped.append("%s (does not exist)" % p)
        elif any(q != d and q.startswith(d.rstrip("/") + "/") for d in folders):
            skipped.append("%s (inside a denied folder)" % p)
        else:
            denies.append(p)
    denies = list(dict.fromkeys(denies))
    denied = [os.path.realpath(ex(p)) for p in denies]
    reads = []
    input_roots = {"~/.codex/attachments", "~/.codex/skills/openai-docs"}
    for p in (p for p, v in snippet_fs.items() if v == "read" and not p.startswith(":")):
        q = ex(p)
        real = os.path.realpath(q)
        if p in input_roots and (real != os.path.abspath(q)
                                 or (os.path.lexists(q) and not os.path.isdir(q))):
            stop("%s must be an existing directory without symlink components" % p)
        if not os.path.exists(q):
            skipped.append("%s (does not exist)" % p)
            continue
        if any(real == d or real.startswith(d.rstrip("/") + "/") for d in denied):
            skipped.append("%s (at or under a denied path)" % p)
            continue
        reads.append(p if real == os.path.normpath(q) else real)
    reads = list(dict.fromkeys(reads))
    if skipped:
        notes.append("note: the Codex profile leaves out " + "; ".join(skipped))

    current = codex.read_text()
    try:
        config = tomllib.loads(current)
    except tomllib.TOMLDecodeError as error:
        stop("%s does not parse: %s" % (codex, error))
    if PROFILE in config.get("permissions", {}):
        stop("%s defines [permissions.%s]; that name belongs to the admin profile in %s/requirements.toml, "
             "so remove it, then rerun" % (codex, PROFILE, codex_etc))
    default = config.get("default_permissions")
    if default not in (None, "workstation", PROFILE):
        stop('%s sets default_permissions = %s; set it to "%s", then rerun' % (codex, json.dumps(default), PROFILE))
    want_line = 'default_permissions = "%s"' % PROFILE
    if default == PROFILE:
        updated = current
    elif default is None:
        updated = want_line + "\n" + current
    else:
        updated = re.sub(r"^default_permissions[ \t]*=.*$", want_line, current, count=1, flags=re.MULTILINE)
    policy = config.get("shell_environment_policy", {})
    if any(key in policy for key in ("exclude", "include_only")):
        stop("%s uses legacy shell environment filters; convert them to shell_environment_policy.filters first" % codex)
    if policy.get("inherit", "core") not in ("core", "none") or policy.get("ignore_default_excludes", False):
        stop("%s needs shell_environment_policy.inherit core or none and ignore_default_excludes false" % codex)
    token = "AGENT_GITHUB_READ_TOKEN"
    if any(name.casefold() == token.casefold() for name in policy.get("set", {})):
        stop("%s must not restore the GitHub read token through shell_environment_policy.set" % codex)
    filters = policy.get("filters", {})
    token_keys = [name for name in filters if name.casefold() == token.casefold()]
    if any(filters[name] != "exclude" for name in token_keys):
        stop("%s must exclude the GitHub read token from shell environments" % codex)
    ca_defaults = snippet["shell_environment_policy"]["set"]
    env_set = policy.get("set", {})
    for target, names in (
            ("SSL_CERT_FILE", ("SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PIP_CERT")),
            ("REQUESTS_CA_BUNDLE", ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT"))):
        ca_file = ca_defaults[target]
        if target in env_set:
            if env_set[target] != ca_file:
                stop("%s selects another trust store; the owner must choose before installing" % target)
        else:
            for name in names:
                value = env_set[name] if name in env_set else os.environ.get(name)
                if value is not None and (name == "SSL_CERT_DIR" or value != ca_file):
                    stop("%s selects another trust store; the owner must choose before installing" % name)
    changes = []
    if config.get("default_permissions") != PROFILE:
        changes.append("set " + want_line)

    def add_entry(table, key, value):
        global updated
        expected = copy.deepcopy(tomllib.loads(updated))
        target = expected
        for part in table.split("."):
            target = target.setdefault(part, {})
        target[key] = value
        header = "[" + table + "]"
        entry = '%s = %s\n' % (json.dumps(key), json.dumps(value))
        match = re.search(r"(?m)^[ \t]*\[" + re.escape(table) + r"\][ \t]*(?:#[^\n]*)?(?:\n|$)", updated)
        if match:
            end = match.end()
            updated = updated[:end] + ("" if updated[:end].endswith("\n") else "\n") + entry + updated[end:]
        else:
            try:
                updated = updated + "\n" + header + "\n" + entry
                tomllib.loads(updated)
            except tomllib.TOMLDecodeError:
                stop("%s: use table form %s before installing" % (codex, header))
        if tomllib.loads(updated) != expected:
            stop("%s: could not safely set %s.%s; adjust the table form before installing" % (codex, table, key))
        changes.append("set " + table + "." + key)

    if "inherit" not in policy:
        add_entry("shell_environment_policy", "inherit", "core")
    if "ignore_default_excludes" not in policy:
        add_entry("shell_environment_policy", "ignore_default_excludes", False)
    if not token_keys:
        add_entry("shell_environment_policy.filters", token, "exclude")
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if name not in env_set:
            add_entry("shell_environment_policy.set", name, ca_defaults[name])
    parsed = tomllib.loads(updated)
    if parsed.get("default_permissions") != PROFILE:
        stop("%s: could not set the managed profile" % codex)
    (stage / "config.toml").write_text(updated)
    (stage / "config.toml.changes").write_text("\n".join(changes) + ("\n" if changes else ""))

    q = json.dumps
    lines = [MARK,
             "# so Full Access and the built-in profiles are refused. Written by install_isolation.sh.",
             "default_permissions = %s" % q(PROFILE), "allow_managed_hooks_only = true", "",
             "[allowed_permission_profiles]", "%s = true" % PROFILE, "",
             "[mcp_servers.github_read.identity]",
             "url = %s" % q(managed["allowedMcpServers"][0]["serverUrl"]), "",
             "[features]", "plugins = false", "apps = false", "",
             "[permissions.%s]" % PROFILE, "extends = %s" % q(body["extends"]), "",
             "[permissions.%s.filesystem]" % PROFILE,
             "glob_scan_max_depth = %d" % snippet_fs["glob_scan_max_depth"]]
    lines += ["%s = %s" % (q(k), q(v)) for k, v in special.items()]
    lines += ["%s = \"read\"" % q(p) for p in reads]
    lines += ["%s = \"deny\"" % q(p) for p in denies]
    roots = snippet_fs.get(ROOTS, {})
    if roots:
        lines += ["", "[permissions.%s.filesystem.%s]" % (PROFILE, q(ROOTS))]
        lines += ["%s = %s" % (q(k), q(v)) for k, v in roots.items()]
    lines += ["", "[permissions.%s.network]" % PROFILE]
    lines += ["%s = %s" % (key, q(value)) for key, value in body["network"].items()]
    lines += ["", "[experimental_network]", "enabled = true",
              "managed_allowed_domains_only = true", "allow_local_binding = false",
              "", "[experimental_network.domains]"]
    lines += ["%s = \"allow\"" % q(host) for host in managed["sandbox"]["network"]["allowedDomains"]]
    requirements = "\n".join(lines) + "\n"
    parsed = tomllib.loads(requirements)
    if parsed["default_permissions"] != PROFILE or parsed["allowed_permission_profiles"] != {PROFILE: True}:
        stop("the Codex requirements did not come out as expected")
    (stage / "requirements.toml").write_text(requirements)

(stage / "notes").write_text("\n".join(notes) + ("\n" if notes else ""))
PY

cp "$swe/.claude/scripts/guard_outward.py" "$swe/.claude/scripts/tells_check.py" \
   "$swe/.claude/scripts/after_summary.sh" "$swe/.claude/scripts/fetch_allow.txt" "$stage/"
/usr/bin/python3 -I -m py_compile "$stage/guard_outward.py" "$stage/tells_check.py"
rm -rf "$stage/__pycache__"

# Managed settings for display only: text values outside permissions, sandbox
# and hook matchers, such as env, helpers and headers, are masked.
masked() {
    /usr/bin/python3 -I -c 'import json, sys
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
mark="# Admin-enforced Codex requirements. Only the profile defined here may run,"
# The requirements file 17def8a installed, before it carried the profile.
predecessor=0cd81bf0aef9a0d63019984800d84ebdfbc548928a48aa611bdc52e918fc69ff
if [ -f "$stage/requirements.toml" ] && [ -f "$codex_etc/requirements.toml" ] \
        && [ "$(head -n 1 "$codex_etc/requirements.toml")" != "$mark" ] \
        && [ "$(sha256sum < "$codex_etc/requirements.toml" | cut -d' ' -f1)" != "$predecessor" ]; then
    echo "install_isolation: $codex_etc/requirements.toml holds policy this script did not write." >&2
    echo "Merge it by hand or move it aside, then rerun." >&2
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
echo "alignment_workstation profile and refuses Full Access, then ask an agent to run"
echo "swe/scripts/check_isolation.sh --client claude, or --client codex, in a fresh"
echo "session of each client."
