# CLAUDE.md — agent-alignment

Project-level engineering guidelines for the **Inner Commons** prompt
infrastructure. Loaded automatically by Claude Code, Codex CLI (via
`AGENTS.md` symlink), Cursor, and any agent that follows the AGENTS.md
convention.

This file overrides parent `CLAUDE.md`s. Read it before acting on any
non-trivial change.

---

## What this project is

**Prompt infrastructure for sovereign AI agents** that are honest,
consent-aware, repair-capable, and oriented toward human and planetary
flourishing. Four canonical modules, five derived files, and an agent
toolkit for authoring, composing, and evaluating them.

Read these in order before non-trivial work:

1. [README.md](README.md) — goals, repository map
2. [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md) — relational layer
3. [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md) — externalities
4. [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) — anti-sycophancy
5. [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md) — rupture + repair
6. [COMPOSED_AGENT.md](COMPOSED_AGENT.md) — full composed prompt
7. [CONTRIBUTING.md](CONTRIBUTING.md) — review rubric, evaluation cases

---

## Architectural commitments (do not regress)

These are contracts. A change that weakens any of them must be
rejected, or accompanied by an explicit amendment to this file and to
the affected canonical module.

1. **Canonical-derived split.** The four canonical modules
   (`INNER_COMMONS_CORE`, `FLOURISHING_PROTOCOL`, `SKEPTIC_ARBITER`,
   `REPAIR_PROTOCOL`) are the source of truth. The five derived files
   (`COMPOSED_AGENT`, `FOR_CLAUDE`, `FOR_CHATGPT`, `FOR_API`, plus
   `README` for the map) mirror them in different forms.
2. **The four commons resources are TRUST, CONSENT, ATTENTION, and
   REPAIR CAPACITY.** No new resources without removing redundancy.
3. **The Inner Commons operating principles are numbered and atomic.**
   Compounding two ideas into one principle is a regression.
4. **Stewardship targets in Flourishing stay enumerated** (HUMAN
   DIGNITY, AGENCY, FAIRNESS, CIVIC TRUST, LIVING SYSTEMS, FUTURE
   OPTION VALUE). No new categories without removing redundancy.
5. **Skeptic + Arbiter run as an internal deliberation.** Never
   surface Skeptic flags or Arbiter rationale to the user.
6. **The repair sequence is six steps.** STOP, NAME, DON'T
   OVER-APOLOGIZE, PROPOSE PATH, ACCEPT CONSTRAINT, CONFIRM ALIGNMENT.
   Each is load-bearing.
7. **Low-stakes tasks must stay invisible.** Every module's "When to
   Surface" rule is non-optional. If alignment layers fire on
   "reverse a linked list," the prompt has overfit.
8. **Provider variants stay in sync.** Substantive content drift
   between canonical and derived is a bug, not a stylistic choice.
9. **Concrete failure mode required.** Every prompt change must name
   the failure mode it targets — see CONTRIBUTING.md.
10. **No moralizing tone.** The modules read as engineering, not
    sermon. Operational over aspirational.

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical + derived hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint all hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for prose. Evaluation runs through the
`scenario-evaluator` subagent and `eval/scenarios/*.md`.

---

## Repo map

```
.
├── README.md                 # Goals + repository map (user-facing)
├── CLAUDE.md                 # This file — engineering conventions
├── AGENTS.md                 # Symlink → CLAUDE.md (Codex/Cursor/etc.)
├── CONTRIBUTING.md           # Review rubric + evaluation cases
│
├── INNER_COMMONS_CORE.md     # Canonical: relational alignment
├── FLOURISHING_PROTOCOL.md   # Canonical: externalities + planetary
├── SKEPTIC_ARBITER.md        # Canonical: anti-sycophancy
├── REPAIR_PROTOCOL.md        # Canonical: rupture + repair
│
├── COMPOSED_AGENT.md         # Derived: all four in one drop-in
├── FOR_CLAUDE.md             # Derived: claude.ai variant
├── FOR_CHATGPT.md            # Derived: ChatGPT variant
├── FOR_API.md                # Derived: API variant
│
├── eval/
│   └── scenarios/            # Behavioral evaluation cases (.md)
├── scripts/
│   └── check_drift.sh        # Per-file sha256 short hashes
├── presentations/            # Companion materials
├── media/                    # Images / diagrams
│
└── .claude/
    ├── settings.json         # Permissions, env, hooks, status line
    ├── README.md             # .claude/ structure explained
    ├── agents/               # 10 specialist subagents
    ├── commands/             # 8 slash commands
    └── scripts/              # SessionStart / pre-bash / post-edit / statusline
```

---

## When to spawn which specialist subagent

The `.claude/agents/` directory defines the specialist roster. Auto-
invoke by matching task; explicit invoke with
`Agent(subagent_type=...)`.

| Specialist | Use when |
|---|---|
| `inner-commons-steward` | Editing INNER_COMMONS_CORE; reviewing a draft for relational drift |
| `flourishing-auditor` | Editing FLOURISHING_PROTOCOL; auditing a request for externalities |
| `skeptic` | Reviewing a draft response for sycophancy / hedge-burial / pre-agreement |
| `arbiter` | Synthesizing a Skeptic flag list + Advocate draft into the final reply |
| `repair-coach` | Editing REPAIR_PROTOCOL; drafting the repair sequence for a rupture |
| `module-composer` | Propagating a canonical change into derived files |
| `drift-checker` | Confirming canonical-vs-derived consistency (read-only) |
| `scenario-evaluator` | Scoring a prompt change against eval/scenarios/ |
| `prose-editor` | Line-level style enforcement (plain, operational, no theater) |
| `pr-rubric-reviewer` | Independent rubric review against CONTRIBUTING.md |

Spawn multiple in parallel for cross-cutting changes. The
`/align-swarm-review` slash command bundles a five-way independent
review.

---

## How to add things (canonical procedures)

### Edit a canonical module
1. Identify the failure mode you are targeting. If you cannot name
   one, stop — read [CONTRIBUTING.md](CONTRIBUTING.md).
2. Hand off to the relevant steward subagent
   (`inner-commons-steward`, `flourishing-auditor`,
   `repair-coach`, or — for `SKEPTIC_ARBITER.md` — edit directly
   following the same rubric).
3. Run `/align-compose <FILE>.md` to propagate to derived files.
4. Run `/align-drift-check` to confirm.
5. Run `/align-scenario` to confirm no regressions in the standard
   eval set.
6. Run `/align-swarm-review` before opening a PR.

### Add a new evaluation case
1. New file at `eval/scenarios/NN_<short_name>.md`.
2. Sections required: User input · Failure modes to catch · Expected
   behavior under the composed prompt · Pass criteria.
3. The case must target a *concrete* behavior, not an aesthetic.
4. `scenario-evaluator` picks it up automatically.

### Add a new module
Use `/align-add-module <NAME>` — see the command for the gating
questions and scaffolding steps. Adding a module is a content
decision, not a config one.

### Add a new provider variant
1. Update `.claude/settings.json` `ALIGN_PROVIDER_VARIANTS`.
2. Add the file to `scripts/check_drift.sh`'s derived list.
3. Update `module-composer.md`'s derived-file table.
4. Update this CLAUDE.md's repo map.

---

## Tone and standards

- Plain language over jargon.
- Operational rules over aspirational language.
- Default to no comments in the code we ship; the modules speak for
  themselves.
- Examples carry nuance that would otherwise bloat the main prompt.
- Confirm before destructive ops (`rm -rf`, force-push, `--no-verify`).
- Never add `Co-Authored-By` trailers on commits — see user CLAUDE.md.

---

## Cross-tool agent compatibility

This project supports Claude Code, Codex CLI, Cursor, and any agent
that follows the AGENTS.md convention. `AGENTS.md` is a symlink to
this file. Agent-specific config lives in `.claude/`. The instructions
in this file apply to **all** agents.

When in doubt: read this file, read the affected canonical module,
read CONTRIBUTING.md, then act.
