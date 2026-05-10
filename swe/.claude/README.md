# swe/.claude/ — SWE-track Claude Code configuration

This directory configures Claude Code (and via the `AGENTS.md`
symlink at the parent of this folder, Codex CLI / Cursor / any
AGENTS.md consumer) for **SWE work in this subtree only**.

## What's checked in

| Path | Purpose |
|---|---|
| [settings.json](settings.json) | Permissions allow/ask/deny lists, env vars, hooks, status line. SWE allowlist (pytest, ruff, mypy, npm, eslint, tsc, cargo, go, make, docker read-only, gh PR/issue read-only, rg). |
| [agents/](agents/) | 12 SWE specialist subagent definitions. |
| [commands/](commands/) | 14 SWE slash commands. |
| [scripts/](scripts/) | Hook + status-line helpers. Shell-only, dependency-free, all guarded with `set -euo pipefail`. |

## What's gitignored

| Path | Why |
|---|---|
| `.claude/settings.local.json` | Personal overrides — never committed. |
| `.claude/cache/` | Claude Code runtime cache. |
| `.claude/projects/` | Per-project Claude Code state. |

---

## Subagent roster (12)

| Name | Tools | Model | Use for |
|---|---|---|---|
| `code-reviewer` | Read, Grep, Glob, Bash | opus | Independent diff review |
| `regression-test-writer` | Read, Grep, Glob, Bash, Write, Edit | sonnet | Failing-test-first for bugs |
| `security-reviewer` | Read, Grep, Glob, Bash | opus | OWASP top-10 review |
| `perf-auditor` | Read, Grep, Glob, Bash | opus | Hot-path / budget audit |
| `dashboard-probe` | Read, Grep, Glob, Bash, Write | sonnet | Headless-Chromium UI verification |
| `dependency-auditor` | Read, Grep, Glob, Bash | sonnet | CVE / license / maintenance audit |
| `architecture-explorer` | Read, Grep, Glob, Bash | sonnet | First-pass repo orientation |
| `refactoring-planner` | Read, Grep, Glob, Bash | opus | Stepwise behavior-preserving refactor plan |
| `debugger` | Read, Grep, Glob, Bash | opus | Root-cause diagnosis |
| `docs-writer` | Read, Edit, Write, Grep, Glob, Bash | sonnet | ADRs, READMEs, runbooks, CHANGELOG |
| `code-skeptic` | Read, Grep, Glob, Bash | opus | Anti-sycophancy flag list over a draft sign-off |
| `code-arbiter` | Read, Grep, Glob, Bash | opus | Synthesize Skeptic flags into final review verdict |

## Slash command roster (14)

| Command | Hands off to |
|---|---|
| `/swe-explore` | `architecture-explorer` |
| `/swe-review` | `code-reviewer` |
| `/swe-add-test` | `regression-test-writer` |
| `/swe-fix-bug` | `debugger` → `regression-test-writer` → `code-reviewer` |
| `/swe-debug` | `debugger` |
| `/swe-perf` | `perf-auditor` |
| `/swe-security` | `security-reviewer` |
| `/swe-deps` | `dependency-auditor` |
| `/swe-refactor` | `refactoring-planner` |
| `/swe-probe` | `dashboard-probe` |
| `/swe-docs` | `docs-writer` |
| `/swe-skeptic` | `code-skeptic` + `code-arbiter` |
| `/swe-swarm-review` | parallel: `code-reviewer`, `security-reviewer`, `perf-auditor`, `dependency-auditor`, `architecture-explorer` |
| `/swe-init` | `architecture-explorer` + `docs-writer` (install protocols in another repo) |

---

## Hook architecture

```
SessionStart  → session_start.sh    surfaces SWE protocol hashes + dispatch table
PreToolUse    → pre_bash_guard.sh   blocks rm -rf / force-push / --no-verify / curl|sh
PostToolUse   → post_edit_verify.sh language-aware (ruff/mypy/eslint/tsc/cargo/go/clang-format)
                                    + canonical-protocol reminders
                                    + dependency-manifest flag for /swe-deps
                                    + .claude/* validation
StatusLine    → statusline.sh       branch + dirty + swe:<canonical-hash>
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
    "SWE_DEBUG": "1"
  }
}
```

---

## Adding a new specialist

1. Drop a markdown file at `agents/<name>.md` with frontmatter
   (`name`, `description`, `tools`, `model`).
2. Make `description` start with "Use proactively when…" to
   encourage auto-delegation, or be neutral for explicit-invoke-only.
3. Body uses the canonical shape:
   - Read first (link to relevant protocols)
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
bash -n .claude/scripts/*.sh
bash -n scripts/*.sh

# Smoke-test the status line and session-start
bash .claude/scripts/statusline.sh
bash .claude/scripts/session_start.sh

# Print canonical hashes
bash scripts/check_drift.sh
```

Subagent and command markdown files are validated by Claude Code at
load time; malformed frontmatter shows up in the `/agents` or
`/commands` list as a load error.
