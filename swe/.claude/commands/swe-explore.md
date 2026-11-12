---
description: Map an unfamiliar codebase fast. Hands off to architecture-explorer; returns a 200-400 word brief with layout, entry points, build/test commands, conventions, and gaps.
argument-hint: "[path-to-repo]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Map an unfamiliar codebase to produce a fast orientation brief.

Input: `$1` is the path to the repo (default: current working
directory).

Steps:

1. Spawn `architecture-explorer` against `$1`. Brief: "produce the
   ARCHITECTURE BRIEF format defined in your agent definition. One
   pass, fast. Cap at 400 words."
2. Surface the brief to the user verbatim.
3. The brief includes a "Recommended next step" line; surface that
   as the suggested next agent or command.

Do not modify any file.
