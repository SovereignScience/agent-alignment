# .claude/: repo-root configuration

This is a **router**. Real `.claude/` infrastructure (settings,
agents, commands, hooks, status line) lives inside the two
track subtrees:

- [`../swe/.claude/`](../swe/.claude/): SWE-track configuration
  (12 SWE subagents, 14 SWE slash commands, language-aware hooks,
  pytest/ruff/mypy/npm/eslint/tsc/cargo/go permissions)
- [`../flourishing/.claude/`](../flourishing/.claude/):
  alignment-track configuration (10 alignment subagents,
  8 align-* commands, drift-check hooks)

## What this root `.claude/` contains

| Path | Purpose |
|---|---|
| [settings.json](settings.json) | Minimal allowlist for read-only navigation; SessionStart + statusLine hooks only. No agents, no commands, no language hooks. Switches off harness attribution on commits and pull requests, and runs the SWE track's guard as a PreToolUse hook when `CLAUDE_CODE_REMOTE` is true. Both are for a one-repository cloud session, which reads this file and nothing from the machine layer. |
| [scripts/cloud_push.sh](scripts/cloud_push.sh) | The one way a cloud session pushes, and only when the owner asks: the current `feature/<ID>-<slug>` branch, or the board with `--board`. It refuses outside a cloud session. |
| [scripts/session_start.sh](scripts/session_start.sh) | Prints a "you're at the router, `cd swe/` or `cd flourishing/`" message at session start. |
| [scripts/statusline.sh](scripts/statusline.sh) | Status line that shows `(router)` to remind that real work happens in a subtree. |

## Why this exists

If an agent opens the repo root in Claude Code without realizing
the dual-track structure, it gets a deliberately minimal context
plus a clear "go to the right subtree" signal. Once the agent
`cd`s into `swe/` or `flourishing/`, that subtree's `.claude/`
loads automatically and provides the right permissions, hooks,
status line, and roster.

## Adding agents / commands / hooks

Don't. Agent infrastructure for a track lives in that track's
`.claude/`. The right move is:

- A new SWE subagent, command or hook goes in `../swe/.claude/`
- A new alignment subagent, command or hook goes in `../flourishing/.claude/`

If you have a genuinely cross-cutting need (rare), raise it with
the owner or extend [`docs/ADR-0001-dual-track.md`](../docs/ADR-0001-dual-track.md)
to capture the rationale before adding back to the root.
