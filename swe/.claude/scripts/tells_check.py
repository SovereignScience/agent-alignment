#!/usr/bin/env python3
"""PostToolUse: point out AI tells in prose a session just wrote, so it rewrites them.

The list follows Wikipedia's "Signs of AI writing" guide plus the user's own rules.
It never blocks; it tells the session what to fix. The guard and the pre-push check
import find_tells from here, so there is one list.
"""
import json
import re
import sys

PATTERNS = [
    ("em or en dash", re.compile("[—–]")),
    ("curly quotes", re.compile("[‘’“”]")),
    ("AI attribution", re.compile(
        r"co-authored-by:[^\n]*(?<![\w-])(claude|anthropic|openai|chatgpt|gpt-|codex|copilot|cursor|gemini)|"
        r"generated (with|by) \[?(claude|ai\b|chatgpt|codex|copilot|cursor)|"
        r"claude-session:|claude\.ai/code/|noreply@anthropic\.com|\U0001F916", re.I)),
    ("emoji", re.compile("[\U0001F300-\U0001FAFF✅❌✨⭐]")),
    ("AI vocabulary", re.compile(
        r"\b(delve[sd]?|delving|tapestry|testament|pivotal|crucial|seamless(ly)?|"
        r"showcas(e|es|ed|ing)|underscor(e|es|ed|ing)\s+(the|a|an|how|that|this|its|their|our)|"
        r"foster(s|ed|ing)?|boasts?|vibrant|groundbreaking|intricate|meticulous(ly)?|"
        r"comprehensive|robust|leverag(e|es|ed|ing)|in the realm of)\b", re.I)),
    ("stock phrase", re.compile(
        r"(it'?s worth noting|it is worth noting|\bin conclusion\b|\bin summary\b|^\s*overall,|"
        r"\badditionally,|\bfurthermore,|\bmoreover,|key takeaways?|why this matters|let'?s dive|"
        r"i hope this helps|great question)", re.I | re.M)),
    ("negative parallelism", re.compile(
        r"\b(not just|not only)\b[^.\n]{0,80}\bbut\b|\bisn'?t just\b|\bit'?s not [^.\n]{1,40}, it'?s\b", re.I)),
    ("copula avoidance", re.compile(r"\b(serves as|stands as)\b", re.I)),
    ("bold-lead bullet", re.compile(r"^\s*([-*]|\d+\.)\s+\*\*[^*\n]+\*\*", re.M)),
    ("bold paragraph lead", re.compile(r"^\*\*[^*\n]{2,60}\*\*", re.M)),
    ("arrow", re.compile("[←→↔⇒]")),
]
PROSE_SUFFIX = (".md", ".txt", ".html", ".rst", ".adoc")


def find_tells(text):
    return [name for name, rx in PATTERNS if rx.search(text or "")]


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tin = data.get("tool_input") or {}
    path = tin.get("file_path") or ""
    if not path.lower().endswith(PROSE_SUFFIX) or path.startswith("/tmp/") \
            or "/.claude/" in path or "/.codex/" in path:
        return
    text = tin.get("content") if data.get("tool_name") == "Write" else tin.get("new_string")
    tells = find_tells(text)
    if tells:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "AI tells in %s: %s. Rewrite those lines in plain words, the way "
                                 "the user writes, before moving on." % (path, ", ".join(tells)),
        }}))


if __name__ == "__main__":
    main()
