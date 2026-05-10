# ADR-0001: Dual-track repository — SWE protocols + Inner Commons alignment

Status: accepted
Date:   2026-04-30

## Context

This repository began as the **Inner Commons** alignment prompt
library — four canonical modules (`INNER_COMMONS_CORE`,
`FLOURISHING_PROTOCOL`, `SKEPTIC_ARBITER`, `REPAIR_PROTOCOL`) plus
provider-specific derived files (`COMPOSED_AGENT`, `FOR_CLAUDE`,
`FOR_CHATGPT`, `FOR_API`). It also shipped a `.claude/` directory
of subagents and slash commands focused entirely on *authoring,
composing, and evaluating those alignment prompts*.

In practice, the same repo holds the agentic-engineering toolkit
the maintainer uses for general software work: language-aware
hooks, sane permissions, dispatch table, status line, multi-agent
review patterns. The two concerns kept colliding:

- An agent landing in this folder for SWE work was greeted with
  alignment-prompt scaffolding and no SWE protocols.
- An agent landing for prompt-authoring work could trip over SWE
  hooks and SWE subagents that were not relevant.
- Documentation was ambiguous about which canonical files were
  authoritative for which use case.

The two halves are genuinely independent — they do not share
content, and an agent typically uses one or the other in a session,
not both. But they share infrastructure (`.claude/settings.json`,
hooks, status line, permissions) and project conventions
(`CLAUDE.md`).

## Decision

Treat this as a **dual-track repository**:

- **Track A — agentic software engineering** ships four canonical
  SWE protocols (`SWE_CORE`, `TESTING_PROTOCOL`,
  `PERFORMANCE_PROTOCOL`, `SECURITY_PROTOCOL`), 10 SWE subagents,
  and 10 SWE slash commands (prefix `/swe-`).
- **Track B — Inner Commons + Flourishing alignment** ships the
  original four canonical modules, the five derived files, 10
  alignment subagents, and 8 slash commands (prefix `/align-`).

Tracks are surfaced explicitly:

- `README.md` opens with a "two tracks" router.
- `QUICKSTART_SWE.md` and `QUICKSTART_FLOURISHING.md` give 30-second
  onboarding per track.
- `CLAUDE.md` has a Track A section (primary) and a Track B section.
- `SessionStart` hook prints both tracks' module hashes and points
  at the matching QUICKSTART.
- Subagent and slash-command names are namespaced — `swe-*` vs.
  `align-*` for commands; descriptive names for subagents
  themselves (no clash within `agents/`).
- Status line shows `swe:<hash>` and `align:<hash>` segments so
  drift in either track is visible at a glance.

Shared infrastructure (`settings.json`, hooks) is intentionally
cross-cutting and serves both tracks.

## Consequences

### Positive
- An agent dropping into the repo can route itself to the right
  track in under 30 seconds.
- Each track stays clean: no SWE conventions leaking into prompt
  authoring, no alignment language leaking into code review.
- Shared infrastructure (one settings.json, one set of hooks)
  avoids duplication and keeps the developer experience
  consistent.
- The SWE protocols are reusable in other repos via `/swe-init`,
  without dragging the alignment library along.

### Negative / costs
- Two tracks means roughly twice the surface area for new
  contributors to skim. Mitigated by the QUICKSTART files and the
  namespaced subagent/command rosters.
- Cross-track changes (e.g. a new hook that serves both tracks)
  need to be designed not to bias one track over the other.
- Drift detection now spans two canonical sets. Mitigated by
  `scripts/check_drift.sh` reporting both.

### Things this commits us to
- Keeping the namespacing strict — `swe-*` for SWE commands,
  `align-*` for alignment commands. No mixed-track agent names.
- Keeping the QUICKSTART files current as either track evolves.
- Keeping `CLAUDE.md` and `README.md` synced with both tracks
  whenever a canonical or roster changes.

## Alternatives considered

- **Split into two repositories.** Cleanest separation, but loses
  the shared `.claude/` infrastructure and forces the maintainer
  to keep two settings.json / hook setups in sync by hand. The
  inner-commons-and-flourishing content also benefits from sitting
  next to a working SWE setup as a reference for what the
  protocols look like in practice.
- **Make alignment the only public concern; keep SWE config in
  `~/.claude/`.** That kept the user-level CLAUDE.md as the only
  source of SWE rigor. Agents in *other* repos could not benefit
  from the SWE protocols, and a SWE agent landing in this repo
  was un-served.
- **Fold SWE protocols into the existing canonical modules under
  the Flourishing umbrella.** Conceptually wrong — code-quality
  rules are not relational alignment rules, and the prompts would
  bloat past the point of being usable.
