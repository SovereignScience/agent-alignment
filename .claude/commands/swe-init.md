---
description: Initialize the SWE protocol stack in a target repository — copy the four canonical SWE protocols, set up an AGENTS.md or CLAUDE.md pointer, and recommend a starting subagent roster. For bringing a new project under the same agentic-engineering discipline.
argument-hint: [target-repo-path]
allowed-tools: Bash, Read, Write, Agent
model: inherit
---

Initialize the SWE protocol stack in a target repository.

Input: `$1` is the path to the target repo (default: current
working directory).

Steps:

1. Spawn `architecture-explorer` against `$1` first — get the
   layout brief so the protocols are sized to the project.
2. Read SWE_CORE.md, TESTING_PROTOCOL.md, PERFORMANCE_PROTOCOL.md,
   SECURITY_PROTOCOL.md from this repo.
3. Ask the user which subset to install. Default: SWE_CORE +
   TESTING for any project; add PERFORMANCE if a hot-path or
   render-loop is in scope; add SECURITY if any trust boundary is
   handled.
4. For each selected protocol, write a copy under
   `$1/docs/swe-protocols/` (or wherever the project keeps its
   conventions). Do not overwrite an existing file with the same
   name without confirmation.
5. Spawn `docs-writer` to write or update `$1/CLAUDE.md` (and
   `$1/AGENTS.md` symlink) with:
   - One paragraph naming the project
   - References to the installed SWE protocols
   - Build / test / lint / typecheck commands extracted from the
     architecture-explorer brief
   - A short dispatch table naming which subagents are most useful
     for this project
6. Surface the diff to the user. Do not commit.

This command never modifies anything outside `$1`. The protocols
are copies, not symlinks, so the target repo can evolve them
independently.
