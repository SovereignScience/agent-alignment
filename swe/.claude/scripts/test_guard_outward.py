"""WebFetch checks in guard_outward.py, driven the way Claude Code calls the hook.

Run: python3 -m unittest discover -s swe/.claude/scripts -p 'test_*.py'
"""
import json
import pathlib
import subprocess
import sys
import unittest

GUARD = pathlib.Path(__file__).with_name("guard_outward.py")


def decision(tool, tool_input):
    """The hook's permission decision for one tool call, or None when it allows it."""
    run = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(
        {"tool_name": tool, "tool_input": tool_input}), capture_output=True, text=True, check=True)
    if not run.stdout.strip():
        return None
    return json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"]


class WebFetchTests(unittest.TestCase):
    def test_documentation_hosts_and_their_subdomains_are_allowed(self):
        for url in ("https://code.claude.com/docs/en/sandboxing",
                    "https://learn.microsoft.com/en-us/windows/wsl/wsl-config",
                    "https://docs.python.org/3/library/socket.html"):
            self.assertIsNone(decision("WebFetch", {"url": url, "prompt": "summarise"}), url)

    def test_other_hosts_are_refused(self):
        for url in ("https://example.com/", "https://code.claude.com.evil.example/",
                    "https://evil.example/?u=code.claude.com", "not a url", ""):
            self.assertEqual(decision("WebFetch", {"url": url, "prompt": "x"}), "deny", url)

    def test_a_url_that_could_carry_data_out_is_refused(self):
        long_query = "https://github.com/search?q=" + "a" * 300
        long_path = "https://github.com/" + "a" * 1100
        for url in (long_query, long_path):
            self.assertEqual(decision("WebFetch", {"url": url, "prompt": "x"}), "deny")

    def test_bash_checks_are_unchanged(self):
        self.assertIsNone(decision("Bash", {"command": "git status"}))
        self.assertEqual(decision("Bash", {"command": "git push origin main"}), "deny")


if __name__ == "__main__":
    unittest.main()
