---
description: Install the five SWE protocols in a target repository as copies, and nothing else. Stops and asks when the target repository belongs to someone else.
argument-hint: "[target-repo-path]"
allowed-tools: Bash, Read, Write
model: inherit
---

Install the five SWE protocols in a target repository.

Input: `$1` is the path to the target repo (default: current
working directory).

Steps:

1. If `$1` is someone else's repository (its remote or history is
   not the user's), stop and ask before writing anything.
2. Read SWE_CORE.md, TESTING_PROTOCOL.md, PERFORMANCE_PROTOCOL.md,
   SECURITY_PROTOCOL.md and SKEPTIC_ARBITER.md from this repo.
3. Write a copy of each under `$1/docs/swe-protocols/` (or wherever
   the project keeps its conventions). Do not overwrite an existing
   file with the same name without confirmation.
4. List the files written to the user. Do not commit.

This command copies the five protocols and nothing else. Never
write `$1/.claude/settings*.json`, `$1/CLAUDE.md` or `$1/AGENTS.md`
unless the user names them in this turn. Agents, commands, scripts
and settings are copied by hand from `swe/.claude/` if wanted. The
protocols are copies, not symlinks, so the target repo can evolve
them independently. This command never modifies anything outside
`$1`.
