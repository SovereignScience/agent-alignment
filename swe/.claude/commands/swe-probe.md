---
description: Headless-browser probe of a local page. Hands off to dashboard-probe, which starts the app and returns a report with DOM rects, computed styles, console messages, failed requests and screenshots. Use to verify a UI fix actually landed before claiming "done".
argument-hint: <url-or-route>
allowed-tools: Bash, Read, Write, Agent
model: inherit
---

Probe a local page to verify UI behavior.

Input: `$ARGUMENTS` is the URL or route to probe. If empty, ask
for the URL.

Steps:

1. If `$ARGUMENTS` is not on localhost or 127.0.0.1, stop: automated
   browsers open local pages only (security rule 12).
2. Find the command that starts the app, from the repository's docs or
   the task; ask once if none says. Do not check the address with curl:
   in a sandboxed session a server started elsewhere cannot be reached,
   so the probe starts the app itself.
3. Spawn `dashboard-probe`. Brief: "probe <address> per your agent
   definition, starting the app with <command>. Capture DOM rects,
   computed styles, console messages, failed requests and screenshots
   before and after the interaction under test. Save screenshots under
   $TMPDIR/probe-<timestamp>/. Cap at 400 words."
4. Surface the verdict and the screenshot paths to the user. If FAIL,
   recommend the next agent (`debugger` for console errors,
   `code-reviewer` for the recent UI diff).
