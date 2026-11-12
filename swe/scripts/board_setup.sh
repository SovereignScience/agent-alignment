#!/usr/bin/env bash
# Set up a project's Lattice board, or bring it back from its private
# repository. Run it yourself, from the top of the project:
#
#   board_setup.sh [--actor human:<name>] [--remote <url>]
#
# With no board in the project it runs lattice init with the settings in
# LATTICE_ONBOARDING.md, writes .lattice/context.md from that file's
# template, keeps .lattice/ and .worktrees/ out of source Git through
# .git/info/exclude, makes the board its own Git repository and commits it.
# The project name is the folder name, the project code its initials, and the
# review page port the first from 8803 that nothing listens on. Change
# dashboard_port in .lattice/config.json if another board already has it.
#
# --remote names the board's private repository. If it already holds a board,
# that board is cloned into .lattice instead of a new one being made, which
# is how a board comes back on another machine. Otherwise the new board is
# pushed there. Without --remote nothing is pushed.
#
# It changes no tracked file and refuses a project that already has .lattice.
set -euo pipefail

die() { echo "board_setup: $*" >&2; exit 1; }

actor="human:${USER:-owner}" remote=""
while [ $# -gt 0 ]; do
    case $1 in
        --actor) [ $# -ge 2 ] || die "--actor needs a value"; actor=$2; shift 2 ;;
        --remote) [ $# -ge 2 ] || die "--remote needs a value"; remote=$2; shift 2 ;;
        *) die "unknown argument $1; usage: $0 [--actor human:<name>] [--remote <url>]" ;;
    esac
done
[[ $actor == human:?* ]] || die "--actor is a person, human:<name>, not $actor"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
guide="$(dirname "$here")/LATTICE_ONBOARDING.md"
[ -f "$guide" ] || die "the onboarding guide is not at $guide"
command -v lattice >/dev/null || die "lattice is not on PATH"
root=$(git rev-parse --show-toplevel 2>/dev/null) || die "this folder is not in a Git repository"
[ "$root" = "$PWD" ] || die "run this from the top of the repository: $root"
[ ! -e .lattice ] || die "this project already has a board in .lattice; nothing was changed"
branch=$(git branch --show-current)
[ -n "$branch" ] || die "the checkout is not on a branch"

restore=no
if [ -n "$remote" ]; then
    if git ls-remote --exit-code "$remote" refs/heads/main >/dev/null 2>&1; then
        restore=yes
    elif [ $? -ne 2 ]; then
        die "cannot reach $remote"
    fi
fi

common=$(git rev-parse --path-format=absolute --git-common-dir)
mkdir -p "$common/info"
for line in .lattice/ /.worktrees/; do
    grep -qxF "$line" "$common/info/exclude" 2>/dev/null || echo "$line" >> "$common/info/exclude"
done

if [ "$restore" = yes ]; then
    git clone -q "$remote" .lattice
    [ -f .lattice/config.json ] || die "$remote holds no board; remove .lattice before trying again"
else
    name=$(basename "$PWD")
    read -r code port < <(python3 - "$name" <<'PY'
import re, socket, sys
words = [w for w in re.split(r"[^A-Za-z]+", sys.argv[1]) if w]
if not words:
    sys.exit("board_setup: the folder name has no letters to make a project code from")
code = ("".join(w[0] for w in words) if len(words) > 1 else words[0])[:5].upper()
def free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0
print(code, next(p for p in range(8803, 8900) if free(p)))
PY
    ) || die "could not work out a project code and port"
    LATTICE_NO_UPDATE_CHECK=1 lattice init --path . --actor "$actor" --project-code "$code" \
        --project-name "$name" --preset linear --workflow classic --review-mode inline \
        --plan-review-mode inline --plan-approval human --done-display all --no-seed \
        --no-setup-claude --no-setup-agents --description "Tasks for the $name repository" >/dev/null \
        || die "lattice init failed; remove .lattice before trying again"
    python3 - "$here" "$guide" "$name" "$code" "$port" "$branch" <<'PY'
import json, os, sys
here, guide, name, code, port, branch = sys.argv[1:]
sys.path.insert(0, here)
from board_context import template as context_template
config = json.load(open(".lattice/config.json"))
config.update(auto_code_review_on_transition=False, auto_plan_review_on_transition=False, dashboard_port=int(port))
config.setdefault("dashboard", {})["theme"] = "holographic"
with open(".lattice/config.json", "w") as out:
    json.dump(config, out, indent=2, sort_keys=True)
    out.write("\n")
template = context_template(open(guide).read())
path = os.getcwd().replace(os.path.expanduser("~"), "~", 1)
swaps = [("# <name>", "# " + name),
         ("<project> at <path>: <what it covers, one or two sentences>.",
          "the %s repository at %s: all work on this repository." % (name, path)),
         ('<other boards with the same conventions, or "None">', "None"),
         ("<tag list, lowercase, one word each>", "to be set after the first session"),
         ("<build or lock down>", "build"),
         ("<branch>", branch), ("<board directory>", path),
         ("<CODE>", code), ("<port>", port)]
for old, new in swaps:
    if old not in template:
        sys.exit("board_setup: the context template in %s has no %r" % (guide, old))
    template = template.replace(old, new)
with open(".lattice/context.md", "w") as out:
    out.write(template)
PY
    git init -q --initial-branch=main .lattice
    for path in events tasks plans artifacts notes archive ids.json config.json context.md .gitignore; do
        if [ -e ".lattice/$path" ]; then git -C .lattice add -- "$path"; fi
    done
    git -C .lattice commit -q -m "chore(board): start the board"
    if [ -n "$remote" ]; then
        git -C .lattice remote add origin "$remote"
        git -C .lattice push -q -u origin main || die "the push to $remote failed; the board is committed here"
    fi
fi

git check-ignore -q .lattice/config.json || die "source Git can still see the board"
LATTICE_ROOT=$PWD LATTICE_NO_UPDATE_CHECK=1 lattice doctor >/dev/null 2>&1 || die "lattice doctor reports a problem; run it here"
python3 - "$restore" "${remote:-none}" <<'PY'
import json, sys
config = json.load(open(".lattice/config.json"))
print("READY: board %s (%s), review page port %s, %s, remote %s" % (
    config["project_code"], config["project_name"], config["dashboard_port"],
    "brought back" if sys.argv[1] == "yes" else "new", sys.argv[2]))
PY
