"""check_isolation.sh against a made-up home, with fake curl and python3, so no network is used.

Run: python3 -m unittest discover -s swe/scripts -p 'test_*.py'
"""
import os
import pathlib
import sys
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check_isolation.sh")
SWE = SCRIPT.parent.parent
FAKE_CURL = '#!/bin/sh\ncase "$*" in *example.com*) exit "${FAKE_EXAMPLE:-7}" ;; *) exit "${FAKE_PYPI:-7}" ;; esac\n'
FAKE_PYTHON = ('#!/bin/sh\ncase "$3" in *AF_UNIX*) printf "%s" "$FAKE_PY_OUT"; exit "${FAKE_PY_EXIT:-0}" ;;\n'
               '*tomllib*) exec "$REAL_PY" "$@" ;; esac\nexit 0\n')
REQUIREMENTS = ('default_permissions = "alignment_workstation"\n\n[allowed_permission_profiles]\n'
                'alignment_workstation = true\n\n[permissions.alignment_workstation]\nextends = ":workspace"\n')
TOOLS = ("cmp", "dirname", "grep", "head", "ls", "rm")
BASH = shutil.which("bash")


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.home = root / "home"
        self.repo = self.home / "projects/repo"
        self.repo.mkdir(parents=True)
        self.sentinel = self.home / ".config/agent-alignment/sentinel"
        self.sentinel.parent.mkdir(parents=True)
        self.etc = root / "etc"
        (self.etc / "claude-code/hooks").mkdir(parents=True)
        (self.etc / "codex").mkdir()
        for name in ("guard_outward.py", "tells_check.py", "after_summary.sh", "fetch_allow.txt"):
            shutil.copy(SWE / ".claude/scripts" / name, self.etc / "claude-code/hooks" / name)
        (self.etc / "codex/requirements.toml").write_text(REQUIREMENTS)
        # Only these tools are on PATH, so a probe that reached for the real curl would fail.
        self.bin = root / "bin"
        self.bin.mkdir()
        for name, text in (("curl", FAKE_CURL), ("python3", FAKE_PYTHON)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        for name in TOOLS:
            (self.bin / name).symlink_to(shutil.which(name))

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, client, sentinel="agent-alignment sentinel", **fake):
        if sentinel is not None:
            self.sentinel.unlink(missing_ok=True)
            self.sentinel.write_text(sentinel)
        env = dict(os.environ, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                   SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                   TMPDIR=str(self.repo), PATH=str(self.bin), REAL_PY=sys.executable)
        env.update({"FAKE_PY_OUT": "refused", **fake})
        args = ["--client", client] if client else []
        run = subprocess.run([BASH, str(SCRIPT), *args], cwd=self.repo, env=env,
                             capture_output=True, text=True, timeout=60)
        return run.returncode, run.stdout + run.stderr

    def test_a_sentinel_is_judged_by_what_opens(self):
        for content, expected in (("agent-alignment sentinel: made-up", "FAIL  sentinel readable"),
                                  ("something else", "FAIL  sentinel opens with other content"),
                                  ("", "FAIL  sentinel is an empty file")):
            with self.subTest(content=content):
                _, out = self.probe("codex", sentinel=content)
                self.assertIn(expected, out)
        self.sentinel.unlink()
        self.sentinel.symlink_to("/dev/null")
        _, out = self.probe("codex", sentinel=None)
        self.assertIn("ok    sentinel masked", out)

    def test_a_sentinel_the_sandbox_hides_leaves_the_result_incomplete(self):
        self.sentinel.unlink(missing_ok=True)
        (self.home / ".cache-agent").mkdir()
        self.home.chmod(0o555)
        try:
            code, out = self.probe("claude", sentinel=None, FAKE_PYPI="0")
        finally:
            self.home.chmod(0o755)
        self.assertEqual(code, 2, out)
        self.assertIn("info  sentinel not visible", out)
        self.assertIn("test -s %s && echo present" % self.sentinel, out)
        self.assertIn("Incomplete", out)
        self.assertNotIn("All checks passed", out)

    def test_network_expectations_follow_the_client(self):
        code, out = self.probe("codex", sentinel="")
        self.assertIn("info  pypi.org not reached", out)
        self.assertIn("an offline machine also reaches nothing", out)
        _, out = self.probe("claude", sentinel="")
        self.assertIn("FAIL  pypi.org not reached", out)
        _, out = self.probe("claude", sentinel="", FAKE_EXAMPLE="0", FAKE_PYPI="0")
        self.assertIn("FAIL  example.com reachable", out)
        (self.bin / "curl").unlink()
        _, out = self.probe("codex", sentinel="")
        self.assertIn("FAIL  curl not found", out)

    def test_only_a_refused_socket_creation_counts(self):
        cases = (({}, "ok    Unix socket creation refused"),
                 ({"FAKE_PY_OUT": "created"}, "FAIL  Unix sockets can be created"),
                 ({"FAKE_PY_OUT": "", "FAKE_PY_EXIT": "1"}, "FAIL  Unix socket test did not run"),
                 ({"FAKE_PY_OUT": "error 97"}, "FAIL  Unix socket test did not run: error 97"))
        for fake, expected in cases:
            with self.subTest(fake=fake):
                _, out = self.probe("claude", sentinel="", **fake)
                self.assertIn(expected, out)

    def test_installed_files_are_compared_with_the_checkout(self):
        _, out = self.probe("codex", sentinel="")
        self.assertIn("ok    installed hook matches this checkout: guard_outward.py", out)
        self.assertIn("ok    installed Codex requirements allow only the alignment_workstation profile", out)
        (self.etc / "codex/requirements.toml").write_text(
            REQUIREMENTS.replace("alignment_workstation = true", "alignment_workstation = true\n\":workspace\" = true"))
        _, out = self.probe("codex", sentinel="")
        self.assertIn("FAIL  installed Codex requirements are missing or allow more", out)
        _, out = self.probe("claude", sentinel="")
        self.assertNotIn("Codex requirements", out)

    def test_a_planted_socket_module_is_not_imported(self):
        (self.bin / "python3").unlink()
        (self.bin / "python3").symlink_to(shutil.which("python3", path=os.environ["PATH"]))
        (self.repo / "socket.py").write_text("print('planted')\nraise SystemExit(0)\n")
        _, out = self.probe("claude", sentinel="")
        self.assertIn("Unix socket", out)
        self.assertNotIn("planted", out)

    def test_a_client_is_required(self):
        code, _ = self.probe(None)
        self.assertEqual(code, 64)


if __name__ == "__main__":
    unittest.main()
