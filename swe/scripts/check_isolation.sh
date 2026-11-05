#!/usr/bin/env bash
# Check, from a fresh session in each client after install_isolation.sh, that
# sandboxed commands work inside the boundary. Run it from a checkout.
#
#   swe/scripts/check_isolation.sh --client claude|codex [--sentinel PATH ...] [PATH ...]
#
# The clients differ on purpose: Claude's sandbox reaches the package
# registries and, with its seccomp filter installed, refuses Unix sockets;
# Codex's workstation profile runs commands without network.
#
# Read access is tested only on sentinel files with made-up content: the
# installer writes ~/.config/agent-alignment/sentinel, and --sentinel adds files
# you created yourself (outside the sandbox) in places that must stay hidden.
# A sentinel that opens with its text is readable. One that opens empty is
# masked and one refused with "Permission denied" is denied. One that looks
# absent may be hidden or missing, so the script lists it for you to confirm
# outside the sandbox.
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
workspace="${SWE_WORKSPACE:-$HOME/projects}"
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
ok() { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; failed=1; }
info() { printf 'info  %s\n' "$1"; }
can_write() {
    local probe="$1/.agent-alignment-probe.$$"
    if ( : > "$probe" ) 2>/dev/null; then rm -f "$probe"; return 0; fi
    return 1
}

for s in "${sentinels[@]}"; do
    if out="$(head -c 128 -- "$s" 2>&1)"; then
        if [ -z "$out" ]; then
            ok "sentinel masked (opens empty): $s"
        elif grep -qF "$sentinel_text" <<<"$out"; then
            bad "sentinel readable: $s"
        else
            bad "sentinel opens with other content, so it proves nothing: $s"
        fi
    else
        case "$out" in
            *"Permission denied"*) ok "sentinel refused: $s" ;;
            *"No such file"*) info "sentinel not visible: $s"; confirm+=("$s") ;;
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
if can_write "$HOME"; then bad "home directory writable"; else ok "home directory not writable"; fi
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
if cmp -s "$here/codex/requirements.toml" "$codex_etc/requirements.toml"; then
    ok "installed Codex requirements match this checkout"
else
    bad "installed Codex requirements differ from this checkout, or are missing: $codex_etc/requirements.toml"
fi

if sock="$(python3 -c 'import socket; socket.socket(socket.AF_UNIX).close()' 2>&1)"; then
    if [ "$client" = claude ]; then
        bad "Unix sockets can be created: the sandbox's optional seccomp filter is missing (npm install -g @anthropic-ai/sandbox-runtime)"
    else
        info "Unix sockets can be created; the Codex profile does not claim to block them"
    fi
else
    case "$sock" in
        *PermissionError*|*"Operation not permitted"*) ok "Unix socket creation refused" ;;
        *) bad "Unix socket test failed for another reason: $(tail -n 1 <<<"$sock")" ;;
    esac
fi
if python3 -c 'import http.server as h; h.ThreadingHTTPServer(("127.0.0.1", 0), h.BaseHTTPRequestHandler).server_close()' 2>/dev/null; then
    info "a local test server can bind 127.0.0.1"
else
    info "a local test server cannot bind 127.0.0.1"
fi

if curl -sS -m 8 -o /dev/null https://example.com 2>/dev/null; then
    bad "example.com reachable"
else
    ok "example.com not reached"
fi
if curl -sS -m 8 -o /dev/null https://pypi.org/simple/ 2>/dev/null; then
    if [ "$client" = claude ]; then ok "pypi.org reachable"; else bad "pypi.org reachable, but Codex commands should have no network"; fi
else
    if [ "$client" = claude ]; then bad "pypi.org not reached"; else ok "pypi.org not reached (an offline machine looks the same)"; fi
fi

if [ "$failed" != 0 ]; then
    echo "Some checks failed."
    exit 1
fi
echo "All checks passed."
if [ "${#confirm[@]}" -gt 0 ]; then
    echo "The sandbox did not show these sentinels. Confirm outside it that each exists:"
    for s in "${confirm[@]}"; do printf '  test -f %q && echo present\n' "$s"; done
fi
