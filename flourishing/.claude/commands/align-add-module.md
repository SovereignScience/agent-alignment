---
description: "Scaffold a new alignment module: write a stub canonical .md, add a section to COMPOSED_AGENT.md, register it in README.md's Repository Map, and propagate to the three provider variants. Use sparingly. Adding modules is a content decision, not a config one."
argument-hint: <module-name>
allowed-tools: Read, Edit, Write, Bash, Agent
model: inherit
---

Scaffold a new canonical alignment module.

Input: `$1` is the proposed module name in `SHOUTY_SNAKE` form, e.g.
`POWER_PROTOCOL` (final filename will be `POWER_PROTOCOL.md`).

Before scaffolding, ask the user:

1. What concrete failure mode does this module target? If they
   cannot name one, do not create the module. Point them at
   `CONTRIBUTING.md` instead.
2. Why is this not absorbable into an existing canonical module?
3. What single example demonstrates the intended behavior change?

If the user clears all three, proceed:

1. Create `$1.md` with frontmatter-style header comments, an
   `<lower_snake_tag>` opening tag, a Purpose section, an
   Operating Principles list (numbered), a "When to Surface"
   section, and at least one example.
2. Update `README.md` Repository Map to list the new file.
3. Hand off to `module-composer` to add a Module 5 section to
   `COMPOSED_AGENT.md` and to propagate stubs into FOR_CLAUDE,
   FOR_CHATGPT, and FOR_API.
4. Update the dispatch table in `CLAUDE.md` if a new specialist
   subagent will own the module.
5. Hand off to `pr-rubric-reviewer` to confirm the scaffold passes
   the five PR-expectation questions.

Do not commit. Surface the diff and let the user decide.
