# Agent Alignment

Prompt infrastructure for sovereign AI systems that are honest, consent-aware, repair-capable, and oriented toward human and planetary flourishing.

This repository packages the current "Inner Commons" prompt family into a composable starter kit for aligned agents. The focus is practical: reduce sycophancy, preserve user agency, make power legible, improve repair after mistakes, and surface broader harms when a request externalizes costs onto other people or living systems.

## Design Goals

- Preserve dignity, consent, and user agency.
- Reduce people-pleasing, strategic agreement, and hollow validation.
- Improve repair competence when the model gets something wrong.
- Make downstream social and ecological externalities legible.
- Keep the system modular enough to compose into provider-specific prompts.

## Quick Start

If you want one file, start with `COMPOSED_AGENT.md`.

If you want modular composition:

1. Start with `INNER_COMMONS_CORE.md`
2. Add `FLOURISHING_PROTOCOL.md`
3. Add `SKEPTIC_ARBITER.md`
4. Add `REPAIR_PROTOCOL.md`

If you want provider-specific variants:

- `FOR_CLAUDE.md`
- `FOR_CHATGPT.md`
- `FOR_API.md`

## Repository Map

| File | Purpose |
|---|---|
| `README.md` | Repository overview and quick start |
| `COMPOSED_AGENT.md` | Full composed prompt with all modules in one file |
| `INNER_COMMONS_CORE.md` | Relational alignment core: trust, consent, attention, repair capacity |
| `FLOURISHING_PROTOCOL.md` | Human and planetary flourishing layer: externalities, public-interest harms, ecological stewardship |
| `SKEPTIC_ARBITER.md` | Anti-sycophancy deliberation layer |
| `REPAIR_PROTOCOL.md` | Rupture detection and repair protocol |
| `FOR_CLAUDE.md` | Claude-oriented full and compact variants |
| `FOR_CHATGPT.md` | ChatGPT-oriented full and compact variants |
| `FOR_API.md` | API-oriented composition guidance and compact system prompt |
| `CONTRIBUTING.md` | Change criteria and review rubric |

## How To Refine This

Use this repo as infrastructure, not scripture. Prompt changes should stay tied to concrete behaviors and test cases:

- What failure mode are we fixing?
- What new failure mode might this create?
- Does the change improve practical alignment or just add moral language?
- Does it stay usable in real products and workflows?

`CONTRIBUTING.md` contains a simple review rubric and suggested evaluation cases.

## Current Shape

The prompt stack now covers four layers:

1. Relational stewardship between user and agent
2. Human and planetary flourishing beyond the immediate dyad
3. Anti-sycophancy internal deliberation
4. Repair competence when things go wrong

That is enough for an initial public repository, not a finished alignment architecture. The next useful refinement step is scenario testing: product design, coding assistants, civic workflows, safety-critical advice, and resource-intensive AI operations all stress these modules differently.

## Source Lineage

The repository is based on Patrick Deegan's 2026 essay *Inner Alignment as a Commons* and extends it with a broader flourishing and externalities layer for sovereign agent infrastructure.
