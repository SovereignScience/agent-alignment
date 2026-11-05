#!/usr/bin/env bash
# Check, from a fresh session in each client after install_isolation.sh, that
# sandboxed commands work inside the boundary. Run it from a checkout.
#
#   swe/scripts/check_isolation.sh [--sentinel PATH ...] [PATH ...]
#
# Read access is tested only on sentinel files with made-up content: the
# installer writes ~/.config/agent-alignment/sentinel, and --sentinel adds files
# you created yourself (outside the sandbox) in places that must stay hidden.
# A sentinel the sandbox does not show passes only because the file exists
# outside it, so create sentinels before running this.
#
# The other PATHs, and the built-in list of credential stores, are reported by
# metadata only: whether the sandbox shows the path at all. That is information,
# not proof of what a process can read, and this script never opens them.
#
# Not covered here: tool calls (WebFetch, WebSearch, Read, Write) and the helpers
# that run outside the sandbox (hooks, the status line, MCP servers).
set -u
workspace="${SWE_WORKSPACE:-$HOME/projects}"
sentinel_text="agent-alignment sentinel"
sentinels=("$HOME/.config/agent-alignment/sentinel")
report=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --sentinel) sentinels+=("${2:?--sentinel needs a path}"); shift 2 ;;
        *) report+=("$1"); shift ;;
    esac
done
failed=0
ok() { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; failed=1; }
info() { printf 'info  %s\n' "$1"; }

for s in "${sentinels[@]}"; do
    if head -c 128 "$s" 2>/dev/null | grep -qF "$sentinel_text"; then
        bad "sentinel readable: $s"
    else
        ok "sentinel not readable: $s"
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

if [ -w "$PWD" ]; then ok "working directory writable"; else bad "working directory not writable"; fi
if [ -w "${TMPDIR:-/nonexistent}" ]; then ok "session temp directory writable"; else bad "session temp directory not writable"; fi
if [ -w "$HOME/.cache-agent" ]; then ok "$HOME/.cache-agent writable"; else bad "$HOME/.cache-agent not writable"; fi
if [ -w "$HOME" ]; then bad "home directory writable"; else ok "home directory not writable"; fi
if [ -e "$HOME/.cache" ] && [ -w "$HOME/.cache" ]; then bad "$HOME/.cache writable"; else ok "$HOME/.cache not writable"; fi
for hooks in "$workspace"/*/.git/hooks; do
    case "$hooks" in "$PWD"/*) continue ;; esac
    [ -e "$hooks" ] || continue
    if [ -w "$hooks" ]; then bad "another checkout's git hooks writable: $hooks"; else ok "another checkout's git hooks not writable"; fi
    break
done

if python3 -c 'import socket; socket.socket(socket.AF_UNIX).close()' 2>/dev/null; then
    bad "Unix sockets can be created: the sandbox's optional seccomp filter is missing (npm install -g @anthropic-ai/sandbox-runtime)"
else
    ok "Unix socket creation refused (seccomp filter present)"
fi
if python3 -c 'import http.server as h; h.ThreadingHTTPServer(("127.0.0.1", 0), h.BaseHTTPRequestHandler).server_close()' 2>/dev/null; then
    ok "a local test server can bind 127.0.0.1"
else
    info "a local test server cannot bind 127.0.0.1 (expected under Codex with network off)"
fi
if curl -sS -m 8 -o /dev/null https://example.com 2>/dev/null; then
    bad "example.com reachable"
else
    ok "example.com refused"
fi
if curl -sS -m 8 -o /dev/null https://pypi.org/simple/ 2>/dev/null; then
    ok "pypi.org reachable"
else
    bad "pypi.org refused"
fi

if [ "$failed" = 0 ]; then echo "All checks passed."; else echo "Some checks failed."; fi
exit "$failed"
