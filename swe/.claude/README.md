# swe/.claude: SWE track configuration for Claude Code

This directory configures Claude Code for work in the swe/ subtree. The
AGENTS.md symlink next to it gives Codex and other AGENTS.md readers the same
instructions; the Codex profile and rules live in ../codex/.

## What is checked in

| Path | Purpose |
|---|---|
| settings.json | Permissions (allow, ask, deny), sandbox, hooks, status line. |
| managed-settings.example.json | The admin-enforced layer for /etc/claude-code/managed-settings.json. |
| agents/ | 12 specialist subagent definitions, each run by name. |
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
  git push, gh writes, kubectl, helm, argocd, ansible, ssh, scp, terraform
  and tofu apply, vault, aws s3 writes, docker push, npm publish, twine,
  crontab, at, systemd-run, tmux send-keys, and the Workflow, RemoteTrigger,
  CronCreate and Artifact tools;
- deny rules for reading credential stores and secret files: ~/.ssh,
  ~/.kube, ~/.config/gh, ~/.aws, ~/.netrc, ~/.gnupg, ~/.password-store,
  ~/.config/age, ~/.docker/config.json, .env files, tfvars, tfstate, age,
  kdbx, pem and key files, id_* keys, and anything named like a token,
  secret or credential;
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
| PreToolUse on Bash and MCP tools | guard_outward.py | Returns a deny decision for pushes, PR and issue writes, cluster, host and cloud changes, messages to third-party services, secret reads, and writes to the guardrail files. Unparsable commands that look outward are denied too. Browser MCP tools (Playwright, Chrome DevTools, Puppeteer) are denied when any argument names a URL off this machine, since MCP servers run outside the Bash sandbox. |
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
unavailable, allows only its own domain list, hides credential files and
token variables, denies the outward commands, runs only managed hooks and
disables bypass mode. Sandboxed commands write only to the working
directory, which the sandbox allows on its own, plus ~/.cache for package
and browser caches and /tmp for scratch files; a parent directory of
checkouts is not writable, so one session cannot edit another project.
To use it, copy guard_outward.py, tells_check.py and after_summary.sh to
/etc/claude-code/hooks/, replace ~/projects with your workspace root, and
install the file as /etc/claude-code/managed-settings.json.

## Codex

../codex/config.snippet.toml holds the permission profile (filesystem
denials, no network) and ../codex/default.rules the commands Codex refuses
in every mode. Codex reads AGENTS.md for the rules themselves.

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
for script in .claude/scripts/*.sh; do bash -n "$script"; done
python3 -m py_compile .claude/scripts/guard_outward.py .claude/scripts/tells_check.py .claude/scripts/pre-push
echo '{"tool_name":"Bash","tool_input":{"command":"git push"}}' | python3 .claude/scripts/guard_outward.py
bash .claude/scripts/statusline.sh
bash .claude/scripts/session_start.sh
```

Malformed agent or command frontmatter shows as a load error in /agents or
/help.
