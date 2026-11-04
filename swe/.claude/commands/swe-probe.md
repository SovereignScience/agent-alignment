---
description: Headless-Chromium probe of a running dashboard. Hands off to dashboard-probe; returns a JSON report with DOM rects, computed styles, console errors, network panel, and screenshots. Use to verify a UI fix actually landed before claiming "done".
argument-hint: <url-or-route>
allowed-tools: Bash, Read, Write, Agent
model: inherit
---

Probe a running dashboard to verify UI behavior.

Input: `$ARGUMENTS` is the URL or route to probe. If empty, ask
for the URL.

Steps:

1. Confirm reachability: `curl -fsS "$ARGUMENTS"`. If not
   reachable, ask the user to start the dev server.
2. Spawn `dashboard-probe`. Brief: "probe per the format defined
   in your agent definition. Capture DOM rects, computed styles,
   console errors, network requests, and screenshots before/after
   the interaction under test. Save artifacts under
   /tmp/probe-<timestamp>/. Cap at 400 words."
3. Surface the verdict + artifact paths to the user. If FAIL,
   recommend the next agent (`debugger` for console errors,
   `code-reviewer` for the recent UI diff).
