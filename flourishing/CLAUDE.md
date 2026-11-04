# CLAUDE.md: agent-alignment / flourishing

Project-level conventions for the **Inner Commons + Flourishing**
alignment-prompt library. Loaded automatically by Claude Code,
Codex CLI (via the `AGENTS.md` symlink), Cursor, and any agent
that follows the AGENTS.md convention.

This file adds to parent and global instructions; it does not loosen them. If you are authoring,
composing, or evaluating alignment prompts in this folder, read
this first; you do not need to read anything outside this subtree.

---

## What this folder is

A four-canonical-module prompt library for sovereign AI agents
that are honest, consent-aware, repair-capable, and oriented toward
human and planetary flourishing. Plus four provider-specific
derived files, ten specialist subagents for authoring / composing /
evaluating, eight slash commands, evaluation scenarios, and the
hooks that keep canonical-vs-derived in sync.

(There is a sibling track in `../swe/` for agentic software-
engineering work. It is independent. You can ignore it.)

---

## Canonical alignment modules (source of truth)

| File | Purpose |
|---|---|
| [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md) | Relational alignment: TRUST / CONSENT / ATTENTION / REPAIR CAPACITY. |
| [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md) | Human and planetary stewardship: externalities, public-interest harms, ecological costs. |
| [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) | Anti-sycophancy on user-facing replies (catches hollow validation, pre-agreement, hedge-burial, sycophancy spirals in conversation). |
| [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md) | Rupture detection + six-step repair sequence. |

## Derived files (provider variants)

| File | Form |
|---|---|
| [COMPOSED_AGENT.md](COMPOSED_AGENT.md) | All four modules in one drop-in. |
| [FOR_CLAUDE.md](FOR_CLAUDE.md) | XML-tagged + abbreviated User-Preferences variant. |
| [FOR_CHATGPT.md](FOR_CHATGPT.md) | ChatGPT system-prompt. |
| [FOR_API.md](FOR_API.md) | API system-prompt + composition guidance. |

---

## Architectural commitments (do not weaken)

These are contracts. A change that weakens any must be rejected,
or accompanied by an explicit amendment to this file and the
affected canonical module.

1. Canonical-derived split. Four canonical modules are the
   source of truth; four derived files mirror them.
2. The four commons resources are TRUST, CONSENT, ATTENTION,
   REPAIR CAPACITY. No new resources without removing redundancy.
3. Operating principles stay numbered and atomic. Compounding
   two ideas into one principle is a regression.
4. Stewardship targets stay enumerated (HUMAN DIGNITY, AGENCY,
   FAIRNESS, CIVIC TRUST, LIVING SYSTEMS, FUTURE OPTION VALUE).
5. Skeptic + Arbiter run as internal deliberation. Never
   surface their flag list or rationale to the user.
6. The repair sequence is six steps. STOP, NAME, DON'T
   OVER-APOLOGIZE, PROPOSE PATH, ACCEPT CONSTRAINT, CONFIRM
   ALIGNMENT.
7. Low-stakes tasks must stay invisible. Every "When to
   Surface" rule is non-optional. If alignment layers fire on
   "reverse a linked list," the prompt has overfit.
8. Provider variants stay in sync. Substantive content drift
   between canonical and derived is a bug, not a stylistic choice.
9. Concrete failure mode required for every prompt change:
   see the rubric in `../CONTRIBUTING.md`.
10. No moralizing tone. Engineering, not sermon. Operational
    over aspirational.
11. No AI co-author trailers. Preserve human co-authors and required provenance.

---

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Edit `INNER_COMMONS_CORE.md` | `inner-commons-steward` | (manual edit) |
| Edit `FLOURISHING_PROTOCOL.md` | `flourishing-auditor` | (manual edit) |
| Edit `REPAIR_PROTOCOL.md` | `repair-coach` (author mode) | (manual edit) |
| Audit a request for material externalities | `flourishing-auditor` (auditor mode) | `/align-flourishing-check` |
| Anti-sycophancy on a draft reply | `skeptic` + `arbiter` | `/align-skeptic` |
| Draft a repair-sequence response | `repair-coach` (coach mode) | `/align-repair` |
| Propagate canonical change to derived | `module-composer` | `/align-compose` |
| Confirm canonical / derived in sync | `drift-checker` | `/align-drift-check` |
| Score a prompt change against eval scenarios | `scenario-evaluator` | `/align-scenario` |
| Line-level prose polish (no content change) | `prose-editor` | (manual) |
| Independent rubric review of a PR | `pr-rubric-reviewer` | (manual) |
| Add a new canonical module (rare) | (orchestrator) | `/align-add-module` |
| Five-way swarm review | (orchestrator) | `/align-swarm-review` |

Dispatch only agents the user requested by name or through an
explicit slash command. Run at most three at once.

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical + derived hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for prose. Evaluation runs through
`scenario-evaluator` and `eval/scenarios/*.md`.

---

## Repo map (this subtree)

```
flourishing/
├── README.md                     # quickstart + dispatch table
├── CLAUDE.md                     # this file
├── AGENTS.md                     # symlink to CLAUDE.md
│
├── INNER_COMMONS_CORE.md         # canonical
├── FLOURISHING_PROTOCOL.md       # canonical
├── SKEPTIC_ARBITER.md            # canonical
├── REPAIR_PROTOCOL.md            # canonical
│
├── COMPOSED_AGENT.md             # derived (all four in one)
├── FOR_CLAUDE.md                 # derived
├── FOR_CHATGPT.md                # derived
├── FOR_API.md                    # derived
│
├── eval/
│   └── scenarios/                # behavioral evaluation cases (.md)
├── scripts/
│   └── check_drift.sh
│
└── .claude/
    ├── settings.json             # alignment-only permissions, hooks, status line
    ├── README.md                 # roster + hook architecture
    ├── agents/                   # 10 specialists
    └── commands/                 # 8 slash commands
```

---

## How to add things

### Edit a canonical module
1. Identify the failure mode you are targeting. If you cannot name
   one, stop. Read `../CONTRIBUTING.md`.
2. Read the relevant module; use a steward only when requested.
3. Propagate affected content to derived files using the documented format.
4. Check affected canonical and derived content for consistency.
5. Check affected scenarios and state the evaluation boundary.
6. Use `/align-swarm-review` only when the user requests that review.

### Add a new evaluation case
1. New file at `eval/scenarios/NN_<short_name>.md`.
2. Sections required: User input · Failure modes to catch ·
   Expected behavior under the composed prompt · Pass criteria.
3. The case must target a *concrete* behavior, not an aesthetic.
4. Include it when the user requests `scenario-evaluator`.

### Add a new module (rare)
Use `/align-add-module <NAME>`. See the command for the gating
questions and scaffolding steps.

### Add a new provider variant
1. Update `.claude/settings.json` `ALIGN_PROVIDER_VARIANTS`.
2. Add the file to `scripts/check_drift.sh`'s derived list.
3. Update `.claude/agents/module-composer.md`'s derived-file table.
4. Update this CLAUDE.md's repo map.

---

## Tone and standards

- Plain language over jargon.
- Operational rules over aspirational language.
- Default to no comments; the modules speak for themselves.
- Examples carry nuance that would otherwise bloat the main prompt.
- Pushes, force-pushes and hook bypasses are denied. History rewrites
  and destructive operations are the user's to run.
- No AI co-author trailers; preserve human co-authors and provenance.

---

## Cross-tool agent compatibility

`AGENTS.md` is a symlink to this file. Agent-specific config lives
in `.claude/`. The instructions in this file apply to **all**
agents that drop into this subtree.

When in doubt: read this file, read `README.md`, read the affected
canonical module, then act.
