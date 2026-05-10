# .claude/ — agent-alignment configuration

This directory configures Claude Code (and via the `AGENTS.md` symlink
at the repo root, Codex CLI / Cursor / any AGENTS.md consumer) for
**both tracks** of this repo:

- **Track A — agentic software engineering** (10 SWE subagents,
  10 SWE slash commands).
- **Track B — Inner Commons + Flourishing alignment** (10 alignment
  subagents, 8 alignment slash commands).

The two tracks share one `.claude/settings.json`, one set of hooks,
and one status line. Subagents and commands are namespaced — `swe-*`
for Track A, `align-*` for Track B (plus the original lowercase-name
alignment subagents).

---

## What's checked in

| Path | Purpose |
|---|---|
| [settings.json](settings.json) | Permissions allow/ask/deny lists, env vars, hooks, status line. Checked in so the whole team gets the same guardrails. Allowlist covers the SWE commands the project uses (pytest, ruff, mypy, npm, eslint, tsc, cargo, go, make, docker, gh, etc.) plus read-only bash. |
| [agents/](agents/) | 20 specialist subagent definitions — see roster below. |
| [commands/](commands/) | 18 slash commands — see roster below. |
| [scripts/](scripts/) | Hook + status-line helpers. Shell-only, dependency-free, all guarded with `set -euo pipefail`. |

## What's gitignored

| Path | Why |
|---|---|
| `.claude/settings.local.json` | Personal overrides — never committed. |
| `.claude/cache/` | Claude Code runtime cache. |
| `.claude/projects/` | Per-project Claude Code state. |

---

## Subagent roster

### Track A — SWE specialists (10)

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

### Track B — alignment specialists (10)

| Name | Tools | Model | Use for |
|---|---|---|---|
| `inner-commons-steward` | Read, Edit, Write, Grep, Glob, Bash | opus | Edit INNER_COMMONS_CORE; review for relational drift |
| `flourishing-auditor` | Read, Edit, Write, Grep, Glob, Bash | opus | Edit FLOURISHING_PROTOCOL; audit a request for externalities |
| `skeptic` | Read, Grep, Glob, Bash | opus | Anti-sycophancy flag list over a draft |
| `arbiter` | Read, Grep, Glob, Bash | opus | Synthesize Skeptic flags into final reply |
| `repair-coach` | Read, Edit, Write, Grep, Glob, Bash | opus | Edit REPAIR_PROTOCOL; draft repair sequence |
| `module-composer` | Read, Edit, Write, Grep, Glob, Bash | sonnet | Propagate canonical to derived |
| `drift-checker` | Read, Grep, Glob, Bash | sonnet | Confirm canonical-vs-derived sync |
| `scenario-evaluator` | Read, Grep, Glob, Bash | opus | Score a prompt change against eval/scenarios/ |
| `prose-editor` | Read, Edit, Write, Grep, Glob, Bash | sonnet | Line-level style enforcement |
| `pr-rubric-reviewer` | Read, Grep, Glob, Bash | opus | Rubric review against CONTRIBUTING.md |

---

## Slash command roster

### Track A — SWE commands (10)

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
| `/swe-swarm-review` | parallel: `code-reviewer`, `security-reviewer`, `perf-auditor`, `dependency-auditor`, `architecture-explorer` |
| `/swe-init` | `architecture-explorer` + `docs-writer` (install protocols in another repo) |

### Track B — alignment commands (8)

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
SessionStart  → session_start.sh    surfaces both-track context + module hashes
PreToolUse    → pre_bash_guard.sh   blocks rm -rf / force-push / --no-verify / curl|sh
PostToolUse   → post_edit_verify.sh language-aware (ruff/mypy/eslint/tsc/cargo/go/clang-format)
                                    + Track A: SWE canonical reminders
                                    + Track B: recompose / drift reminders
                                    + dependency-manifest flag for /swe-deps
                                    + .claude/* validation
StatusLine    → statusline.sh       branch + dirty + swe:hash + align:hash
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
2. Make `description` start with "Use proactively when…" to
   encourage auto-delegation, or be neutral for explicit-invoke-only.
3. Body becomes the system prompt. Use the canonical shape:
   - Read first
   - Invariants you defend
   - How you work
   - What you do not do
   - Report back with
4. Update the dispatch table in [CLAUDE.md](../CLAUDE.md) and the
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

# Print canonical / derived hashes
bash scripts/check_drift.sh
```

Subagent and command Markdown files are validated by Claude Code at
load time; malformed frontmatter shows up in the `/agents` or
`/commands` list as a load error.
