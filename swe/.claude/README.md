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
only managed hooks, starts no MCP server it does not list (none by
default) and disables bypass mode.

Sandboxed commands read nothing in the home directory except the
workspace and the toolchain folders the file lists, and nothing under
/mnt/c on WSL. They write only to the working directory, which the sandbox
allows on its own, the session's temporary directory and ~/.cache-agent,
the package and browser cache the managed env points tools at. A parent directory of
checkouts is not writable, so one session cannot plant a git hook or a
virtualenv in another project. The file tools refuse reads and writes
outside the session's working directories. With the sandbox's optional seccomp
filter installed (npm install -g @anthropic-ai/sandbox-runtime), sandboxed
commands cannot create Unix sockets; without it they can, so
check_isolation.sh treats the filter as a prerequisite. A loopback HTTP
server still binds, inside the sandbox's own network namespace.

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

Paths only one machine has, such as a production checkout to hide or a
conda folder to read, go in a local file outside git, started from
managed-local.example.json. It may only add denials and read paths.
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
~/.config/agent-alignment/managed-local.json. Restart every session
afterwards, then have an agent run swe/scripts/check_isolation.sh in a
fresh session of each client. It tests read access only on sentinel files
with made-up content, and reports real credential paths by metadata alone.
The preview prints rules and paths, never a setting's value; apply backs up
each file under a unique name and prints the commands that undo it.

## Codex

../codex/config.snippet.toml holds the permission profile (filesystem
denials, no network) and ../codex/default.rules the commands Codex refuses
in every mode. Codex reads AGENTS.md for the rules themselves.
install_isolation.sh adds the profile's read denials, and the local
file's, to ~/.codex/config.toml. It stops when that file grants one of
those paths, lacks the workstation profile or does not start on it, and it
installs codex/requirements.toml as /etc/codex/requirements.toml so that
only that profile may run (Codex 0.138.0 or later). Confirm in the CLI and
the VS Code extension that sessions start on it and Full Access is refused.
The profile is a deny list, not Claude's default-deny home read.
default.rules forbids ansible-playbook as a top-level command, so syntax
checks in Codex go through the repository's own validation script.

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
