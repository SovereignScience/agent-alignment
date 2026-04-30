# .claude/ — agent-alignment configuration

This directory configures Claude Code (and via the `AGENTS.md` symlink
at the repo root, Codex CLI / Cursor / any AGENTS.md consumer) to
operate as an Inner-Commons-aware specialist team for *authoring,
composing, and evaluating* alignment prompts.

## What's checked in

| Path | Purpose |
|---|---|
| [settings.json](settings.json) | Permissions allow/ask/deny lists, env vars, hooks, status line. Checked in so the whole team gets the same guardrails. |
| [agents/](agents/) | 10 specialist subagent definitions: `inner-commons-steward`, `flourishing-auditor`, `skeptic`, `arbiter`, `repair-coach`, `module-composer`, `drift-checker`, `scenario-evaluator`, `prose-editor`, `pr-rubric-reviewer`. |
| [commands/](commands/) | Slash commands: `/align-compose`, `/align-drift-check`, `/align-skeptic`, `/align-repair`, `/align-flourishing-check`, `/align-scenario`, `/align-add-module`, `/align-swarm-review`. |
| [scripts/](scripts/) | Hook + status-line helpers. Shell-only, dependency-free, all guarded with `set -euo pipefail`. |

## What's gitignored

| Path | Why |
|---|---|
| `.claude/settings.local.json` | Personal overrides — never committed. |
| `.claude/cache/` | Claude Code runtime cache. |
| `.claude/projects/` | Per-project Claude Code state. |

## How the pieces fit together

- **[CLAUDE.md](../CLAUDE.md)** at the repo root is the source of truth
  for project conventions. Every agent reads it.
- **[AGENTS.md](../AGENTS.md)** is a symlink to CLAUDE.md so non-Claude
  agents that follow the AGENTS.md convention get the same context.
- The `agents/` roster narrows tools and scope per lane (e.g.
  `skeptic` is read-only, `module-composer` can edit derived files).
- The `commands/` set captures repeated workflows so they run
  identically every time.
- The `scripts/session_start.sh` hook surfaces module hashes at the
  top of context.
- The `scripts/pre_bash_guard.sh` hook hard-blocks destructive /
  auth-bypass patterns.
- The `scripts/post_edit_verify.sh` hook reminds about recompose when
  a canonical module is touched, validates settings.json after an
  edit, and lints hook scripts after a write.
- The `scripts/statusline.sh` shows branch, dirty count, and the
  short canonical commitment so prompt drift is visible at all times.

## Customizing locally

Per-developer changes go in `.claude/settings.local.json`, which is
gitignored. That file's keys are merged with `settings.json` — useful
for adding personal `allow` entries without affecting the team.

Example `settings.local.json`:

```json
{
  "permissions": {
    "allow": ["Bash(my-personal-tool *)"]
  },
  "env": {
    "ALIGN_DEBUG": "1"
  }
}
```

## Adding a new specialist

1. Drop a markdown file at `agents/<name>.md` with frontmatter
   (`name`, `description`, `tools`, `model`).
2. Make `description` start with "Use proactively when…" to encourage
   auto-delegation, or be neutral for explicit-invoke-only.
3. Body becomes the system prompt. Keep it short, focused on what the
   agent defends, and link to the docs the agent reads first.
4. Update the dispatch table in [CLAUDE.md](../CLAUDE.md).

## Adding a new slash command

1. Drop a markdown file at `commands/<name>.md` with frontmatter
   (`description`, `argument-hint`, `allowed-tools`).
2. Body is the command prompt. Use `$1`, `$2`, etc. for positional
   args, or `$ARGUMENTS` for the full unparsed argument string.
3. Multi-step workflows that hand off to specialists should name the
   `subagent_type` explicitly.

## Sanity check

After modifying agent / command / hook / settings files:

```bash
# Validate JSON
python3 -c "import json; json.load(open('.claude/settings.json'))"

# Lint hook scripts
bash -n .claude/scripts/*.sh
bash -n scripts/*.sh

# Smoke-test the status line
bash .claude/scripts/statusline.sh

# Print canonical / derived hashes
bash scripts/check_drift.sh
```

Subagent and command Markdown files are validated by Claude Code at
load time; malformed frontmatter shows up in the `/agents` or
`/commands` list as a load error.
