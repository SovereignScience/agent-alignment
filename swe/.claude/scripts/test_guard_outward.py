"""WebFetch checks in guard_outward.py, driven the way Claude Code calls the hook.

Run: python3 -m unittest discover -s swe/.claude/scripts -p 'test_*.py'
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

GUARD = pathlib.Path(__file__).with_name("guard_outward.py")


def decision(tool, tool_input, guard=GUARD):
    """The hook's permission decision for one tool call, or None when it allows it."""
    run = subprocess.run([sys.executable, str(guard)], input=json.dumps(
        {"tool_name": tool, "tool_input": tool_input}), capture_output=True, text=True, check=True)
    if not run.stdout.strip():
        return None
    return json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"]


class MonitorTests(unittest.TestCase):
    def test_monitor_commands_get_the_same_checks_as_bash(self):
        tin = {"description": "x", "timeout_ms": 1000}
        self.assertEqual(decision("Monitor", dict(tin, command="git push origin main")), "deny")
        self.assertIsNone(decision("Monitor", dict(tin, command="tail -f build.log")))


class HookPathTests(unittest.TestCase):
    def test_hooks_ignore_helpers_planted_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = pathlib.Path(tmp, "bin")
            fake.mkdir()
            marker = pathlib.Path(tmp, "ran")
            for name in ("cat", "git"):
                (fake / name).write_text("#!/bin/sh\ntouch %s\necho HIJACKED\nexit 1\n" % marker)
                (fake / name).chmod(0o755)
            env = dict(os.environ, PATH="%s:%s" % (fake, os.environ["PATH"]))
            out = subprocess.run(["/bin/sh", str(GUARD.with_name("after_summary.sh"))], env=env,
                                 capture_output=True, text=True, timeout=30).stdout
            self.assertIn("hookSpecificOutput", out)
            repo = pathlib.Path(tmp, "repo")
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                            "-m", "fixture"], cwd=repo, check=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                                  check=True).stdout.strip()
            subprocess.run(["/usr/bin/python3", "-I", str(GUARD.with_name("pre-push")), "origin", "url"], cwd=repo,
                           env=env, input="refs/heads/main %s refs/heads/main %s\n" % (head, "0" * 40),
                           capture_output=True, text=True, timeout=60)
            self.assertFalse(marker.exists())


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

    def test_a_url_the_client_could_read_as_another_host_is_refused(self):
        for url in ("https://evil.example\\@code.claude.com/x", "https://user@code.claude.com/",
                    "https://code.claude.com:8443/docs", "ftp://code.claude.com/",
                    "https://code.claude.com/a b"):
            self.assertEqual(decision("WebFetch", {"url": url, "prompt": "x"}), "deny", url)

    def test_a_url_that_could_carry_data_out_is_refused(self):
        long_query = "https://github.com/search?q=" + "a" * 300
        long_path = "https://github.com/" + "a" * 1100
        for url in (long_query, long_path):
            self.assertEqual(decision("WebFetch", {"url": url, "prompt": "x"}), "deny")

    def test_the_local_list_adds_hosts_and_a_missing_seed_list_refuses_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            guard = pathlib.Path(tmp, GUARD.name)
            shutil.copy(GUARD, guard)
            url = {"url": "https://intranet.example.org/doc", "prompt": "x"}
            self.assertEqual(decision("WebFetch", url, guard), "deny")
            shutil.copy(GUARD.with_name("fetch_allow.txt"), tmp)
            pathlib.Path(tmp, "fetch_allow.local.txt").write_text("# ours\nexample.org\n")
            self.assertIsNone(decision("WebFetch", url, guard))
            self.assertIsNone(decision("WebFetch", {"url": "https://code.claude.com/docs", "prompt": "x"}, guard))

    def test_bash_checks_are_unchanged(self):
        self.assertIsNone(decision("Bash", {"command": "git status"}))
        self.assertEqual(decision("Bash", {"command": "git push origin main"}), "deny")


class TellsTests(unittest.TestCase):
    """The commit-message check, run the way the managed hook runs the guard."""

    def managed(self, guard, command):
        with tempfile.TemporaryDirectory() as cwd:
            run = subprocess.run(["/usr/bin/python3", "-I", str(guard)], input=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": command}}), capture_output=True, text=True,
                check=True, cwd=cwd)
        return json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"] if run.stdout.strip() else None

    def test_commit_message_tells_are_refused_under_the_managed_invocation(self):
        self.assertEqual(self.managed(GUARD, "git commit -m 'feat: delve into the parser'"), "deny")
        self.assertIsNone(self.managed(GUARD, "git commit -m 'fix: parse empty headers'"))

    def test_attached_and_trailer_messages_are_read_too(self):
        self.assertEqual(self.managed(GUARD, "git commit -m'feat: delve into the parser'"), "deny")
        self.assertEqual(self.managed(
            GUARD, "git commit -m 'fix: x' --trailer 'Co-Authored-By: Claude <noreply@anthropic.com>'"), "deny")
        self.assertIsNone(self.managed(GUARD, "git commit -am'fix: parse empty headers'"))

    def test_a_missing_checker_refuses_commit_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            lone = pathlib.Path(tmp, "guard_outward.py")
            shutil.copy(GUARD, lone)
            shutil.copy(GUARD.with_name("fetch_allow.txt"), tmp)
            self.assertEqual(self.managed(lone, "git commit -m 'fix: parse empty headers'"), "deny")


if __name__ == "__main__":
    unittest.main()
