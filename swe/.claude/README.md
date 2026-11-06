# swe/.claude: SWE track configuration for Claude Code

This directory configures Claude Code for work in the swe/ subtree. The
AGENTS.md symlink next to it gives Codex and other AGENTS.md readers the same
instructions; the Codex profile and rules live in ../codex/.

## What is checked in

| Path | Purpose |
|---|---|
| settings.json | Permissions (allow, ask, deny), sandbox, hooks, status line. |
| managed-settings.example.json | The admin-enforced layer for /etc/claude-code/managed-settings.json. |
| managed-local.example.json | Template for one machine's own paths, installed as managed-settings.d/50-local.json. |
| agents/ | 13 specialist subagent definitions, each run by name. |
| commands/ | 14 slash commands. |
| scripts/ | Hooks and the status line. Need bash, python3, git and sha256sum. |

Personal overrides go in .claude/settings.local.json, which is ignored in
every subtree. Under a managed layer agents cannot write that file; the user
edits it.

## The boundary

The sandbox and the deny list are the boundary. The allow list runs
interpreters, build tools and test runners, so it is a convenience, not a
control. The hooks are guards: they catch what the rules miss and explain
the refusal, and they can fail. Where a managed layer sets
allowManagedHooksOnly, only the managed hooks run and the project hooks in
settings.json are ignored; this directory is for repositories without one.

settings.json carries:

- deny rules for common outward commands and live-system changes:
  git push, gh writes, kubectl, helm, argocd, ssh, scp, terraform
  and tofu apply, vault, aws s3 writes, docker push, npm publish, twine,
  crontab, at, systemd-run, tmux send-keys, and the Workflow, RemoteTrigger,
  CronCreate and Artifact tools;
- deny rules for reading credential stores and secret files: ~/.ssh,
  ~/.kube, ~/.config/gh, ~/.aws, ~/.netrc, ~/.gnupg, ~/.password-store,
  ~/.config/age, ~/.docker/config.json, .env files, tfvars, tfstate, age,
  kdbx, pem and key files and id_* keys. Name patterns such as *token*
  are left out: they hide library files (PyYAML's tokens.py) and never
  reach the home directory, which the managed layer's default-deny read
  covers. Ansible is left to the guard, which allows --syntax-check and
  the list options and refuses every other run;
- deny rules for editing this directory's settings, scripts, agents and
  commands, the user's ~/.claude settings, hooks, agents and CLAUDE.md,
  ~/.codex and /etc/claude-code;
- a fail-closed sandbox block with registry and research domains, project
  and cache writes, and credential denials. Immutable domain restrictions need
  the managed layer below; a project allowlist alone is not that boundary.

The OS sandbox enforces its configured file and network limits. Command
patterns and hooks are partial checks, not proof that every interpreter,
connector or browser action is read-only.

Outward actions are denied, not asked. The agent prepares the change and
the user pushes, posts or applies it in their own terminal.

## Hooks

| Event | Script | What it does |
|---|---|---|
| SessionStart | session_start.sh | Prints the branch, the protocol hashes and the roster. |
| SessionStart on compact, resume, fork | after_summary.sh | Tells the session to re-read the rules and resume only the last request. |
| PreToolUse on Bash, WebFetch and MCP tools | guard_outward.py | Returns a deny decision for pushes, PR and issue writes, cluster, host and cloud changes, messages to third-party services, secret reads, and writes to the guardrail files. WebFetch runs outside the sandbox's network allowlist, so the guard refuses a fetch to a host outside fetch_allow.txt and fetch_allow.local.txt, or with a URL longer than its limits. Unparsable commands that look outward are denied too. Browser MCP tools (Playwright, Chrome DevTools, Puppeteer) are denied when any argument names a URL off this machine, since MCP servers run outside the Bash sandbox. That check reads tool arguments only: redirects, subresources and URLs built by page scripts are not covered, so the server's own origin flags and the sandbox stay the boundary. |
| PostToolUse on Write and Edit | tells_check.py | Points out AI tells in prose the session just wrote, so it rewrites them. Never blocks. |
| PostToolUse on Write and Edit | post_edit_verify.sh | Names the file-level check for the session to run (hooks run outside the sandbox, so it runs no project tool), leaves broad checks to the task checkpoint, and validates .claude files. Never blocks. |

pre-push is a git hook for the user, not a Claude hook. It shows what is
about to leave the machine and asks for a y when a push has more than 3
commits, more than 80 added doc lines, more than 400 added lines, a new doc
file, an AI tell in docs or commit messages, or AI attribution anywhere. It
refuses when there is no terminal. Install it with tells_check.py beside it:

```bash
(
  set -eu
  hook_dir="$(git rev-parse --git-path hooks)"
  for name in pre-push pre-push.local tells_check.py; do
    if [ -e "$hook_dir/$name" ] || [ -L "$hook_dir/$name" ]; then
      echo "Existing $name; preserve and integrate it before installing." >&2
      exit 1
    fi
  done
  mkdir -p "$hook_dir"
  source_dir="$(git rev-parse --show-toplevel)/swe/.claude/scripts"
  cp "$source_dir/pre-push" "$source_dir/tells_check.py" "$hook_dir/"
  chmod +x "$hook_dir/pre-push"
)
```

The scripts assume the default branch is origin/HEAD and fall back to
origin/main.

## Managed layer

managed-settings.example.json is the admin-enforced file this track was
written against. It requires the sandbox, fails closed when the sandbox is
unavailable, allows only package registries on the network, hides
credential files and token variables, denies the outward commands, runs
only managed hooks, allows only the MCP servers it lists (none by
default) and disables bypass mode. Servers a client builds in, such as the
VS Code extension's own, are not on that list and still run.

Sandboxed commands and the file tools see only the session's working
directories: blockReadsOutsideWorkingDirectories hides the rest of the home
directory from both. To commands the rest of home is an empty throwaway
folder, so writes there never reach the disk. The file also denies a named
list of secret locations and /mnt/c, in case that setting changes. Commands
write only to the working directory, the session's temporary directory and
~/.cache-agent, the package and browser cache the managed env points tools
at. A parent directory of checkouts is not writable, so one session cannot
plant a git hook or a virtualenv in another project. With the sandbox's optional seccomp
filter installed (npm install -g @anthropic-ai/sandbox-runtime), sandboxed
commands cannot create Unix sockets; without it they can, so
check_isolation.sh treats the filter as a prerequisite. A loopback HTTP
server still binds, inside the sandbox's own network namespace.

Keep git worktrees inside the checkout, at .worktrees/<name> with
/.worktrees/ in .git/info/exclude (../LATTICE_ONBOARDING.md). This policy
makes the sandbox admin-required, so Claude Code ignores allowWrite and
additionalDirectories in a repository's own .claude settings, and a grant in
~/.claude/settings.json would open the folder to every session.

Sessions meet these limits by design. When one blocks a step, the agent hands
the owner the exact command instead of working around it:

- Python tools cannot use HTTPS: the *.pem deny also hides certifi's CA
  bundle, so pip, pip-compile and pip-audit fail. Ansible Galaxy, the
  Terraform registry, GitHub and every other host off the allowlist are
  unreachable.
- Anything that needs a Unix socket fails: Terraform providers, so validate
  and plan, and Ansible past --syntax-check, whose task queue starts a local
  RPC server. Tests that run them fail in the sandbox and pass in the owner's
  terminal.
- Files matching the secret patterns are masked inside the project too. They
  cannot be read, edited or deleted, and the guard refuses commands that read
  them, even a made-up test file.
- Home is the throwaway folder above, so config written there is gone after
  the command. Use the project, the session's temporary directory or
  ~/.cache-agent.
- git status in the sandbox lists placeholder devices the sandbox mounts over
  protected names (.bashrc, .gitconfig, .mcp.json, .vscode, .claude/hooks and
  others). They are not on disk; leave them. A command run from a subfolder
  leaves an empty .claude/.cc-writes folder there, so run commands from the
  project root and pass paths.
- A worktree outside the project, such as a production checkout kept from
  agents, shows as prunable. Never run git worktree prune; the owner locks
  such worktrees with git worktree lock.

Blocks prepared for the owner run in a subshell with set -euo pipefail, so a
failed step stops the rest, and carry any script inline: a file in the
session's temporary directory can be changed by any session before the owner
runs it.

Two documented settings break the sandbox on Linux and are left out. A
denyRead of ~/ with allowRead exceptions leaves the working directory
read-only, so the sandbox cannot create its mount points for protected files,
and CLAUDE_CODE_SUBPROCESS_ENV_SCRUB makes it mask the containerd socket,
which fails when /run/containerd is not listable; its stub mode also leaves
empty package, lock and .env files in each checkout, hidden by a block it
appends to .git/info/exclude on every run. The token variables named
in credentials.envVars are stripped instead. Rerun check_isolation.sh after
each Claude Code update.

Tools installed in the home directory, such as a lattice venv in ~/.local,
are hidden from agents too. Install the ones agents need root-owned under
/opt, so agents can run them but not change them:

```bash
url=https://github.com/Stage-11-Agentics/lattice.git
sudo /usr/bin/python3 -I -m venv /opt/lattice
sudo /opt/lattice/bin/python -I -m pip install --no-cache-dir \
  "lattice_tracker @ git+$url@$(git ls-remote "$url" refs/heads/main | cut -f1)"
sudo ln -s /opt/lattice/bin/lattice /usr/local/bin/lattice
```

Keep your own copy on the same commit; both write the same boards.

This isolates shell commands and limits the file tools; it does not contain
the agent itself. Hooks, the status line and any MCP server the managed file
lists run with your full access and inherit the managed env, so a listed
MCP server that starts programs from ~/.cache-agent would run what a
sandboxed command left there. WebSearch sends queries to the search
service, the registries accept uploads made with anyone's credentials, a
listed WebFetch host can receive a short query, and sessions on this machine
can message each other; isolatePeerMachines only asks before messages to
other machines. The session temporary directory is shared by every session
of one account. Code, scripts and dependencies an agent wrote stay untrusted
until you review them for a credentialed run. Containing the whole agent
needs a boundary around it, such as a separate account, WSL distro or VM
that holds none of your secrets.

Paths only one machine has, such as a production checkout or a token file
to hide, go in a local file outside git, started from
managed-local.example.json. It may only add denials; the installer refuses
allowRead, for the reason above.
To let WebFetch read another host, add it to
/etc/claude-code/hooks/fetch_allow.local.txt with sudoedit; the
installer copies fetch_allow.txt and never writes the local list.

Install both, with the hooks, from a reviewed checkout:

```bash
swe/scripts/install_isolation.sh           # shows every change, writes nothing
swe/scripts/install_isolation.sh --apply   # backs up each file, then installs
```

Set SWE_WORKSPACE to the folder that holds your checkouts and
SWE_MANAGED_LOCAL to the local file if it is not at
~/.config/agent-alignment/managed-local.json. The preview prints rules and
paths, never a setting's value. It stops, writing nothing, on a symlinked or
irregular target, on a managed directory that is a symlink, not owned by root
or writable by group or others, and on Codex requirements this script did
not write. Apply backs up each file under a unique name and prints the
commands that undo it.

Restart every session afterwards. In a fresh session of each client, have
an agent run:

```bash
swe/scripts/check_isolation.sh --client claude   # or --client codex
```

It tests read access only on sentinel files with made-up content, reports
real credential paths by metadata alone, and checks that the installed hooks
match the checkout. It exits 0 when every check passed, 1 when one failed,
and 2 when the result is incomplete until you run the outside checks it
prints, such as confirming that a sentinel it could not see exists. Then
check by hand, in the same session, what a shell script cannot: the agent's Read of ~/.config/agent-alignment/sentinel is
refused, a WebFetch of https://example.com is refused, and in Codex the
session runs on the alignment_workstation profile and refuses Full Access.

## Codex

../codex/config.snippet.toml holds the Codex settings and the permission
profile body (filesystem denials, no network), and ../codex/default.rules the
commands Codex refuses in every mode. Codex reads AGENTS.md for the rules
themselves. Codex accepts an allowlist only of profiles defined in the
requirements file, so install_isolation.sh writes that body, plus the local
file's denials, into /etc/codex/requirements.toml as alignment_workstation,
the default and the only profile allowed (Codex 0.138.0 or later), and points
default_permissions in ~/.codex/config.toml at it. As in Codex's documented
workspace-only profile, it denies every read (":root") and reopens only
Codex's runtime set (":minimal") and the paths the snippet lists, so files in
other projects stay unreadable; the named denials remain a second layer.

Codex's sandbox cannot mask a symlink or a missing path. A symlinked denial is
replaced by its target, or left out when the target is already denied, and
missing paths are left out; the preview lists both. Rerun the installer after
creating a file that should be denied. It stops when ~/.codex/config.toml is
missing, defines alignment_workstation itself or picks another default, and
when /etc/codex/requirements.toml holds policy it did not write. Without
~/.codex it leaves Codex alone. Confirm in the CLI and the VS Code extension
that sessions start on alignment_workstation and that Full Access is refused.
The profile is a deny list, not Claude's working-directory limit.

default.rules does not forbid ansible-playbook: in the profile's sandbox it
has no network, keys or vault passwords, so syntax checks run and nothing
reaches a host. An allow rule would run a command outside the sandbox, so
none is added. ssh, scp and sftp stay forbidden.

## Adding a specialist

1. Add agents/<name>.md with frontmatter: name, description, tools, model.
2. Set model to inherit and write the description as "Run only when the
   user asks for it by name or invokes its command", then what it returns.
3. Body: read first, invariants, how you work, what you do not do, report
   back with.
4. Update the dispatch table in ../CLAUDE.md and the roster in ../README.md.

## Adding a slash command

1. Add commands/<name>.md with frontmatter: description, argument-hint,
   allowed-tools.
2. The body is the prompt. Use $1, $2 or $ARGUMENTS for arguments.
3. Hand off to specialists with an explicit subagent_type, at most three at
   once.

## Sanity check

```bash
python3 -c "import json; json.load(open('.claude/settings.json'))"
for script in .claude/scripts/*.sh scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s .claude/scripts -p 'test_*.py'
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m py_compile .claude/scripts/guard_outward.py .claude/scripts/tells_check.py .claude/scripts/pre-push
echo '{"tool_name":"Bash","tool_input":{"command":"git push"}}' | python3 .claude/scripts/guard_outward.py
bash .claude/scripts/statusline.sh
bash .claude/scripts/session_start.sh
```

Malformed agent or command frontmatter shows as a load error in /agents or
/help.
