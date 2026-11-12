#!/usr/bin/env bash
# Check, from a fresh session in each client after install_isolation.sh, that
# sandboxed commands work inside the boundary. Run it from a checkout.
#
#   swe/scripts/check_isolation.sh --client claude|codex [--sentinel PATH ...] [PATH ...]
#
# The clients differ on purpose: Claude's sandbox reaches the package
# registries and, with its seccomp filter installed, refuses Unix sockets;
# Codex's alignment_workstation profile uses a managed host-filtering proxy.
#
# Read access is tested only on sentinel files with made-up content: the
# installer writes ~/.config/agent-alignment/sentinel, and --sentinel adds files
# you created yourself (outside the sandbox) in places that must stay hidden.
# A sentinel that opens with its text is readable. One the sandbox replaces
# with /dev/null is masked, and one refused with "Permission denied" is denied.
# An empty file is no evidence. One that looks absent may be hidden or missing.
#
# Exit status: 0 when every check passed, 1 when one failed, 2 when the result
# is incomplete until you run the separate session or outside checks it
# prints: Codex's denied-host request, a sentinel the sandbox did not show,
# or a marker it wrote to a home directory on tmpfs.
#
# The other PATHs, and the built-in list of credential stores, are reported by
# metadata only: whether the sandbox shows the path at all. That is information,
# not proof of what a process can read, and this script never opens them.
#
# Not covered here; check them by hand in the same fresh session: the file
# tools (ask the agent to Read the sentinel: refused), WebFetch (ask it to fetch
# https://example.com: refused by the guard), the effective Codex profile and
# Full Access refusal, and the helpers that run outside the sandbox (hooks, the
# status line, MCP servers).
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${SWE_WORKSPACE:-$(dirname "$(dirname "$(git -C "$here" rev-parse --path-format=absolute --git-common-dir)")")}"
etc="${SWE_ETC:-/etc/claude-code}"
codex_etc="${SWE_CODEX_ETC:-/etc/codex}"
sentinel_text="agent-alignment sentinel"
sentinels=("$HOME/.config/agent-alignment/sentinel")
report=()
client=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --client) client="${2:?--client needs claude or codex}"; shift 2 ;;
        --sentinel) sentinels+=("${2:?--sentinel needs a path}"); shift 2 ;;
        *) report+=("$1"); shift ;;
    esac
done
case "$client" in
    claude|codex) ;;
    *) echo "usage: $0 --client claude|codex [--sentinel PATH ...] [PATH ...]" >&2; exit 64 ;;
esac
failed=0
confirm=()
separate=()
ok() { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; failed=1; }
info() { printf 'info  %s\n' "$1"; }
can_write() {
    local probe="$1/.agent-alignment-probe.$$"
    if ( : > "$probe" ) 2>/dev/null; then rm -f "$probe"; return 0; fi
    return 1
}

for s in "${sentinels[@]}"; do
    if [ -c "$s" ]; then
        ok "sentinel masked (replaced with a device): $s"
    elif out="$(head -c 128 -- "$s" 2>&1)"; then
        if [ -z "$out" ]; then
            bad "sentinel is an empty file, so it proves nothing; rerun install_isolation.sh: $s"
        elif grep -qF "$sentinel_text" <<<"$out"; then
            bad "sentinel readable: $s"
        else
            bad "sentinel opens with other content, so it proves nothing: $s"
        fi
    else
        case "$out" in
            *"Permission denied"*) ok "sentinel refused: $s" ;;
            *"No such file"*) info "sentinel not visible: $s"; confirm+=("$(printf 'test -s %q && echo present' "$s")") ;;
            *) bad "sentinel could not be tested: $s: $out" ;;
        esac
    fi
done

for path in ~/.ssh ~/.aws ~/.config/gh ~/.config/doctl ~/.bash_history ~/.claude ~/.mozilla \
            ~/.config/chromium /mnt/c/Users "${report[@]}"; do
    if [ -d "$path" ] && [ -n "$(ls -A "$path" 2>/dev/null)" ]; then
        info "listed by the sandbox (metadata only): $path"
    elif [ -f "$path" ] && [ -s "$path" ]; then
        info "shown with a size (metadata only): $path"
    else
        info "not shown, or empty: $path"
    fi
done

if can_write "$PWD"; then ok "working directory writable"; else bad "working directory not writable"; fi
if can_write "${TMPDIR:-/tmp}"; then ok "temp directory writable"; else bad "temp directory not writable"; fi
home_marker="$HOME/.agent-alignment-home-probe.$$"
if ! ( : > "$home_marker" ) 2>/dev/null; then
    ok "home directory not writable"
elif [ "$(stat -f -c %T "$HOME" 2>/dev/null)" = tmpfs ]; then
    info "home directory writable, on tmpfs; left $home_marker to check from outside"
    confirm+=("$(printf 'test -e %q && rm -f -- %q && echo present   # writes to the sandbox home reached your home' "$home_marker" "$home_marker")")
else
    rm -f "$home_marker"
    bad "home directory writable"
fi
if [ -d "$HOME/.cache" ] && can_write "$HOME/.cache"; then bad "$HOME/.cache writable"; else ok "$HOME/.cache not writable"; fi
if [ "$client" = claude ]; then
    if can_write "$HOME/.cache-agent"; then ok "$HOME/.cache-agent writable"; else bad "$HOME/.cache-agent not writable"; fi
fi
for hooks in "$workspace"/*/.git/hooks; do
    case "$hooks" in "$PWD"/*) continue ;; esac
    [ -d "$hooks" ] || continue
    if can_write "$hooks"; then bad "another checkout's git hooks writable: $hooks"; else ok "another checkout's git hooks not writable"; fi
    break
done

for f in guard_outward.py tells_check.py after_summary.sh fetch_allow.txt; do
    if cmp -s "$here/.claude/scripts/$f" "$etc/hooks/$f"; then
        ok "installed hook matches this checkout: $f"
    else
        bad "installed hook differs from this checkout, or is missing: $etc/hooks/$f"
    fi
done
if [ "$client" = codex ]; then
    if python3 -I -c 'import sys, tomllib
r = tomllib.load(open(sys.argv[1], "rb"))
p = "alignment_workstation"
sys.exit(0 if r.get("default_permissions") == p and r.get("allowed_permission_profiles") == {p: True}
         and p in r.get("permissions", {}) else 1)' "$codex_etc/requirements.toml" 2>/dev/null; then
        ok "installed Codex requirements allow only the alignment_workstation profile"
    else
        bad "installed Codex requirements are missing or allow more than alignment_workstation: $codex_etc/requirements.toml"
    fi
    if python3 -I -c 'import sys, tomllib
fs = tomllib.load(open(sys.argv[1], "rb")).get("permissions", {}).get("alignment_workstation", {}).get("filesystem", {})
sys.exit(0 if fs.get(":root") == "deny" else 1)' "$codex_etc/requirements.toml" 2>/dev/null; then
        ok "installed Codex profile denies reads outside the paths it reopens"
    else
        bad "installed Codex profile does not deny reads by default (\":root\" = \"deny\"): $codex_etc/requirements.toml"
    fi
    if python3 -I -c 'import sys, tomllib
r = tomllib.load(open(sys.argv[1], "rb"))
n = r.get("experimental_network", {})
p = r.get("permissions", {}).get("alignment_workstation", {}).get("network", {})
m = r.get("mcp_servers", {}).get("github_read", {}).get("identity", {})
sys.exit(0 if n.get("enabled") is True and n.get("managed_allowed_domains_only") is True
         and n.get("allow_local_binding") is False and p.get("allow_local_binding") is False
         and n.get("domains", {}).get("pypi.org") == "allow" and p.get("enabled") is True
         and m.get("url") == "https://api.githubcopilot.com/mcp/readonly" else 1)' "$codex_etc/requirements.toml" 2>/dev/null; then
        ok "installed Codex policy requires the managed proxy and the GitHub read-only endpoint"
    else
        bad "installed Codex network or GitHub read policy differs from this checkout"
    fi
fi

# Import first, then classify only the error from creating the socket.
sock="$(python3 -I -c '
import errno, socket
try:
    socket.socket(socket.AF_UNIX).close()
except OSError as error:
    print("refused" if error.errno in (errno.EPERM, errno.EACCES) else "error %s" % error.errno)
else:
    print("created")' 2>/dev/null)"
case "$sock" in
    refused) ok "Unix socket creation refused" ;;
    created)
        if [ "$client" = claude ]; then
            bad "Unix sockets can be created: the sandbox's optional seccomp filter is missing (npm install -g @anthropic-ai/sandbox-runtime)"
        else
            info "Unix sockets can be created; the Codex profile does not claim to block them"
        fi ;;
    *) bad "Unix socket test did not run: ${sock:-python3 failed before creating a socket}" ;;
esac
if python3 -I -c 'import http.server as h; h.ThreadingHTTPServer(("127.0.0.1", 0), h.BaseHTTPRequestHandler).server_close()' 2>/dev/null; then
    info "a local test server can bind 127.0.0.1"
else
    info "a local test server cannot bind 127.0.0.1"
fi

if ! command -v curl >/dev/null; then
    bad "curl not found, so the network checks did not run"
else
    if [ "$client" = codex ]; then
        separate+=("curl -sS -m 8 -o /dev/null https://example.com")
    elif curl -sS -m 8 -o /dev/null https://example.com 2>/dev/null; then
        bad "example.com reachable"
    else
        ok "example.com not reached"
    fi
    if curl --fail -sS -m 8 -o /dev/null https://pypi.org/simple/pip/ 2>/dev/null; then
        ok "pypi.org reachable"
    else
        bad "pypi.org not reached; approved network access is not verified"
    fi
fi

if [ "${#separate[@]}" -gt 0 ]; then
    echo "Separate checks, each as its own command in this session:"
    for c in "${separate[@]}"; do printf '  %s\n' "$c"; done
    echo "Record an explicit client policy denial; DNS, TLS and timeout errors do not count."
fi
if [ "${#confirm[@]}" -gt 0 ]; then
    echo "Outside checks, for your own terminal:"
    for c in "${confirm[@]}"; do printf '  %s\n' "$c"; done
fi
if [ "$failed" != 0 ]; then
    echo "Some checks failed."
    exit 1
fi
if [ "${#confirm[@]}" -gt 0 ] || [ "${#separate[@]}" -gt 0 ]; then
    echo "Incomplete: no check failed, but the result waits on the checks above."
    exit 2
fi
echo "All checks passed."
