# ADR-0001: Dual-track repository — SWE protocols + Inner Commons alignment

Status: accepted (revised 2026-05-10 to hard-split layout)
Date:   2026-04-30 (original) · 2026-05-10 (revised)

## Context

This repository began as the **Inner Commons** alignment prompt
library — four canonical modules (`INNER_COMMONS_CORE`,
`FLOURISHING_PROTOCOL`, `SKEPTIC_ARBITER`, `REPAIR_PROTOCOL`) plus
provider-specific derived files (`COMPOSED_AGENT`, `FOR_CLAUDE`,
`FOR_CHATGPT`, `FOR_API`). It also held a `.claude/` directory of
subagents and slash commands focused entirely on *authoring,
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

A first revision (April 30) introduced both tracks side-by-side at
the repo root, namespaced by command prefix (`/swe-*` vs
`/align-*`). It worked, but reading the root still required
disambiguating the two tracks on every glance, and the agent files
were intermixed in a single `.claude/agents/`.

A May 10 revision pushed the separation further into a **hard
physical split**: each track lives in its own subtree with its own
`.claude/`, its own canonical protocols, its own scripts, and its
own self-contained README/CLAUDE/AGENTS.

## Decision

Treat this as a **dual-track repository with hard physical split**:

- **`swe/`** — agentic software engineering. Five canonical
  protocols (`SWE_CORE`, `TESTING_PROTOCOL`, `PERFORMANCE_PROTOCOL`,
  `SECURITY_PROTOCOL`, `SKEPTIC_ARBITER`), 12 SWE subagents,
  14 SWE slash commands (prefix `/swe-`), language-aware hooks.
- **`flourishing/`** — Inner Commons + Flourishing alignment. The
  four original canonical modules, four derived provider variants,
  10 alignment subagents, 8 align-* commands, drift-check hooks,
  the eval-scenario suite.

Each track owns:

- Its own `README.md` (start-here for that track)
- Its own `CLAUDE.md` (project conventions, no cross-track refs)
- Its own `AGENTS.md` symlink → CLAUDE.md
- Its own `.claude/` (settings.json, agents/, commands/, scripts/,
  README.md)
- Its own `scripts/check_drift.sh` (operates on that track's files)

The repo root contains:

- A minimal `README.md` and `CLAUDE.md`, both routers — they
  describe the two tracks and tell readers to `cd` into one.
- A `CONTRIBUTING.md` with track-specific rubrics.
- A minimal root `.claude/` whose only job is a `SessionStart` and
  `statusLine` that say "you're at the router; cd into a track."
  No agents, no commands, no language hooks at the root.
- `docs/` (this ADR), `presentations/`, `media/`.

The two `SKEPTIC_ARBITER.md` files coexist intentionally:

- `swe/SKEPTIC_ARBITER.md` targets *engineering* sycophancy
  (hollow approvals, unverified completion claims, hedge-burial of
  bugs).
- `flourishing/SKEPTIC_ARBITER.md` targets *relational* sycophancy
  (hollow validation in user-facing replies, pre-agreement with
  the question's framing, sycophancy spirals across turns).

Same Three-Voices pattern (Advocate / Skeptic / Arbiter), different
failure surface, different agents (`code-skeptic`/`code-arbiter`
in swe vs `skeptic`/`arbiter` in flourishing). They do not interact.

## Consequences

### Positive
- An agent dropping into either subtree gets exactly one set of
  protocols, one `.claude/` configuration, one dispatch table, one
  status line — and nothing about the other track. "Just follow
  what's in the folder" works.
- Each track is independently usable. `swe/` can be copied verbatim
  into another repo (or installed via `/swe-init`) without
  dragging the alignment library along; `flourishing/` is the
  prompt library on its own.
- The two `SKEPTIC_ARBITER.md` files give each track a focused
  anti-sycophancy module appropriate to its failure surface,
  without conflating engineering review with user-facing relational
  dynamics.
- Slash command and agent name clashes are avoided by directory,
  not by prefix gymnastics — Claude Code naturally loads only the
  `.claude/` of the current working tree.

### Negative / costs
- Some duplication: each `.claude/scripts/` carries its own copy
  of `pre_bash_guard.sh` (which is identical between tracks). This
  is accepted because *zero shared scripts* makes each subtree
  truly portable to another repo.
- The `flourishing/SKEPTIC_ARBITER.md` and `swe/SKEPTIC_ARBITER.md`
  share a name. We accept this because the file lives inside its
  track's directory — the name only collides if you treat the two
  tracks as one project.
- Cross-track refactors (e.g. promoting a pattern that emerged in
  one track) require explicit adaptation rather than a shared edit.

### Things this commits us to
- Keeping each track fully self-contained. No references from
  `swe/CLAUDE.md` to `flourishing/`, or vice versa, beyond a
  one-line "sibling track exists; ignore it" footnote.
- Keeping the root deliberately minimal. The root is a router;
  any temptation to add a "global" agent or command goes into one
  of the two tracks instead.
- Keeping the SKEPTIC_ARBITER pattern parallel: any change to the
  Three-Voices structure in one track should be considered for the
  other (separately, by hand — not by automation).

## Alternatives considered

- **Split into two repositories.** Cleanest separation, but loses
  the shared `CONTRIBUTING.md` and the lineage signal that the SWE
  protocols emerged from the same author who built the alignment
  library. Hard split inside one repo gives most of the benefit
  without forcing two repos to be kept in sync by hand.
- **Keep both tracks at the root with namespaced `swe-*` /
  `align-*` commands** (the April 30 revision). Worked, but
  reading the root and the single `.claude/agents/` still required
  every reader to disambiguate per file. The hard split removes
  that cognitive overhead entirely.
- **Make alignment the only public concern; keep SWE config in
  `~/.claude/`.** Lost the ability for agents in *other* repos to
  benefit from the SWE protocols.
- **Fold SWE protocols into the existing canonical modules under
  the Flourishing umbrella.** Conceptually wrong — code-quality
  rules are not relational alignment rules, and the prompts would
  bloat past the point of being usable.
