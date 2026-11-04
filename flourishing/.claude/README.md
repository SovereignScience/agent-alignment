# flourishing/.claude/: alignment-track Claude Code configuration

This directory configures Claude Code (and via the `AGENTS.md`
symlink at the parent of this folder, Codex CLI / Cursor / any
AGENTS.md consumer) for **alignment-prompt-authoring work in this
subtree only**.

## What's checked in

| Path | Purpose |
|---|---|
| [settings.json](settings.json) | Permissions allow/ask/deny lists, env vars, hooks, status line. Alignment-track allowlist (read-only bash, gh PR/issue read-only, jq, sha256sum, repo scripts). No language toolchains: alignment work is prose, not code. |
| [agents/](agents/) | 10 alignment specialist subagent definitions. |
| [commands/](commands/) | 8 alignment slash commands. |
| [scripts/](scripts/) | Hook + status-line helpers. Shell-only, dependency-free, all guarded with `set -euo pipefail`. |

## What's gitignored

| Path | Why |
|---|---|
| `.claude/settings.local.json` | Personal overrides, never committed. |
| `.claude/cache/` | Claude Code runtime cache. |
| `.claude/projects/` | Per-project Claude Code state. |

---

## Subagent roster (10)

| Name | Tools | Model | Use for |
|---|---|---|---|
| `inner-commons-steward` | Read, Edit, Write, Grep, Glob, Bash | inherit | Edit INNER_COMMONS_CORE; review for relational drift |
| `flourishing-auditor` | Read, Edit, Write, Grep, Glob, Bash | inherit | Edit FLOURISHING_PROTOCOL; audit a request for externalities |
| `skeptic` | Read, Grep, Glob, Bash | inherit | Anti-sycophancy flag list over a draft user-facing reply |
| `arbiter` | Read, Grep, Glob, Bash | inherit | Synthesize Skeptic flags into the final user-facing reply |
| `repair-coach` | Read, Edit, Write, Grep, Glob, Bash | inherit | Edit REPAIR_PROTOCOL; draft repair sequence from a transcript |
| `module-composer` | Read, Edit, Write, Grep, Glob, Bash | inherit | Propagate canonical to derived |
| `drift-checker` | Read, Grep, Glob, Bash | inherit | Confirm canonical-vs-derived sync |
| `scenario-evaluator` | Read, Grep, Glob, Bash | inherit | Score a prompt change against eval/scenarios/ |
| `prose-editor` | Read, Edit, Write, Grep, Glob, Bash | inherit | Line-level style enforcement |
| `pr-rubric-reviewer` | Read, Grep, Glob, Bash | inherit | Rubric review against `../CONTRIBUTING.md` |

## Slash command roster (8)

| Command | Hands off to |
|---|---|
| `/align-compose` | `module-composer` + `drift-checker` |
| `/align-drift-check` | `drift-checker` |
| `/align-skeptic` | `skeptic` + `arbiter` |
| `/align-repair` | `repair-coach` |
| `/align-flourishing-check` | `flourishing-auditor` (auditor mode) |
| `/align-scenario` | `scenario-evaluator` |
| `/align-add-module` | scaffold + `module-composer` + `pr-rubric-reviewer` |
| `/align-swarm-review` | parallel: `inner-commons-steward`, `flourishing-auditor`, `repair-coach`, `drift-checker`, `pr-rubric-reviewer` |

---

## Hook architecture

```
SessionStart  runs session_start.sh    surfaces canonical + derived hashes + dispatch table
PreToolUse    runs pre_bash_guard.sh   blocks rm -rf / force-push / --no-verify / curl|sh
PostToolUse   runs post_edit_verify.sh canonical edit: recompose reminder
                                       derived edit: drift-check reminder
                                       .claude/* validation
StatusLine    runs statusline.sh       branch + dirty + align:<canonical-hash>
```

All hooks are best-effort; PostToolUse never blocks. PreToolUse
returns exit 2 to block destructive bash patterns.

---

## Customizing locally

Per-developer changes go in `.claude/settings.local.json`, which is
gitignored. That file's keys are merged with `settings.json`.

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

---

## Adding a new specialist

1. Drop a markdown file at `agents/<name>.md` with frontmatter
   (`name`, `description`, `tools`, `model`).
2. State that it runs only when requested by name or through an
   explicit slash command. Set `model` to `inherit`.
3. Body uses the canonical shape:
   - Read first (link to relevant canonical modules)
   - Invariants you defend
   - How you work
   - What you do not do
   - Report back with
4. Update the dispatch table in [../CLAUDE.md](../CLAUDE.md) and the
   roster above.

## Adding a new slash command

1. Drop a markdown file at `commands/<name>.md` with frontmatter
   (`description`, `argument-hint`, `allowed-tools`).
2. Body is the command prompt. Use `$1`, `$2`, etc. for positional
   args, or `$ARGUMENTS` for the full unparsed argument string.
3. Multi-step workflows hand off to specialists with explicit
   `subagent_type`.

## Sanity check

After modifying agent / command / hook / settings files:

```bash
# Validate JSON
python3 -c "import json; json.load(open('.claude/settings.json'))"

# Lint hook scripts
for script in .claude/scripts/*.sh scripts/*.sh; do bash -n "$script" || exit; done

# Smoke-test the status line and session-start
bash .claude/scripts/statusline.sh
bash .claude/scripts/session_start.sh

# Print canonical / derived hashes
bash scripts/check_drift.sh
```

Subagent and command markdown files are validated by Claude Code at
load time; malformed frontmatter shows up in the `/agents` or
`/commands` list as a load error.
