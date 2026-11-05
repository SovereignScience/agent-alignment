#!/usr/bin/env bash
# Read-only check, run by an agent inside the sandbox after install_isolation.sh,
# that the boundary holds. It opens no secret: it tests whether paths can be read
# or written, which sockets open, and which hosts answer. Run it from a checkout.
#
#   swe/scripts/check_isolation.sh [path that must stay unreadable ...]
#
# Not covered here, because they are tool calls rather than shell commands: ask
# the agent to WebFetch https://example.com (refused by the guard) and to Read a
# file outside its working directories (refused by Claude Code).
set -u
workspace="${SWE_WORKSPACE:-$HOME/projects}"
failed=0
ok() { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; failed=1; }

# A directory counts as readable when it shows any non-empty file.
readable() {
    if [ -d "$1" ]; then
        [ -n "$(find "$1" -maxdepth 3 -type f -size +0 -print -quit 2>/dev/null)" ]
    else
        [ -s "$1" ]
    fi
}
hidden() {
    if [ ! -e "$1" ]; then ok "absent: $1"
    elif readable "$1"; then bad "readable: $1"
    else ok "hidden: $1"; fi
}
seen() { if readable "$1"; then ok "readable: $1"; else bad "hidden: $1"; fi; }
writable() { if [ -w "$1" ]; then ok "writable: $1"; else bad "not writable: $1"; fi; }
fenced() { if [ -e "$1" ] && [ -w "$1" ]; then bad "writable: $1"; else ok "not writable: $1"; fi; }

for path in ~/.ssh ~/.aws ~/.config/gh ~/.config/doctl ~/.bash_history ~/.claude/projects \
            ~/.mozilla ~/.config/chromium /mnt/c/Users "$@"; do
    hidden "$path"
done
seen "$PWD"
writable "$PWD"
writable "${TMPDIR:-/tmp}"
writable "$HOME/.cache-agent"
fenced "$HOME"
fenced "$HOME/.cache"
for hooks in "$workspace"/*/.git/hooks; do
    case "$hooks" in "$PWD"/*) continue ;; esac
    fenced "$hooks"
    break
done

if python3 -c 'import socket; socket.socket(socket.AF_UNIX).close()' 2>/dev/null; then
    bad "unix sockets open (D-Bus, Docker, WSL interop reachable)"
else
    ok "unix sockets blocked"
fi
if python3 -c 'import http.server as h; h.ThreadingHTTPServer(("127.0.0.1", 0), h.BaseHTTPRequestHandler).server_close()' 2>/dev/null; then
    ok "loopback HTTP server binds inside the sandbox"
else
    bad "loopback HTTP server refused"
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
