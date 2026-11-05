"""check_isolation.sh against a made-up home, with fake curl and python3, so no network is used.

Run: python3 -m unittest discover -s swe/scripts -p 'test_*.py'
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check_isolation.sh")
SWE = SCRIPT.parent.parent
FAKE = '#!/bin/sh\nif [ "$FAKE_EXIT" = 0 ]; then exit 0; fi\necho "$FAKE_ERR" >&2\nexit "$FAKE_EXIT"\n'


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
        shutil.copy(SWE / "codex/requirements.toml", self.etc / "codex/requirements.toml")
        self.bin = root / "bin"
        self.bin.mkdir()
        for name in ("curl", "python3"):
            (self.bin / name).write_text(FAKE)
            (self.bin / name).chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, client, sentinel=None, exit_code="1", err="PermissionError: [Errno 1] Operation not permitted"):
        if sentinel is not None:
            self.sentinel.write_text(sentinel)
        env = dict(os.environ, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                   SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                   TMPDIR=str(self.repo), PATH="%s:%s" % (self.bin, os.environ["PATH"]),
                   FAKE_EXIT=exit_code, FAKE_ERR=err)
        args = ["--client", client] if client else []
        run = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.repo, env=env,
                             capture_output=True, text=True, timeout=60)
        return run.returncode, run.stdout + run.stderr

    def test_a_sentinel_is_judged_by_what_opens(self):
        cases = (("agent-alignment sentinel: made-up", "FAIL  sentinel readable"),
                 ("something else", "FAIL  sentinel opens with other content"),
                 ("", "ok    sentinel masked"))
        for content, expected in cases:
            with self.subTest(content=content):
                _, out = self.probe("codex", sentinel=content)
                self.assertIn(expected, out)
        self.sentinel.unlink()
        _, out = self.probe("codex")
        self.assertIn("info  sentinel not visible", out)
        self.assertNotIn("FAIL  sentinel", out)

    def test_network_expectations_follow_the_client(self):
        _, out = self.probe("codex", sentinel="")
        self.assertIn("ok    pypi.org not reached", out)
        _, out = self.probe("claude", sentinel="")
        self.assertIn("FAIL  pypi.org not reached", out)

    def test_only_a_permission_error_counts_as_a_refused_socket(self):
        _, out = self.probe("claude", sentinel="")
        self.assertIn("ok    Unix socket creation refused", out)
        _, out = self.probe("claude", sentinel="", err="ModuleNotFoundError: No module named 'socket'")
        self.assertIn("FAIL  Unix socket test failed for another reason", out)

    def test_installed_files_are_compared_with_the_checkout(self):
        _, out = self.probe("codex", sentinel="")
        self.assertIn("ok    installed hook matches this checkout: guard_outward.py", out)
        (self.etc / "codex/requirements.toml").write_text("# other\n")
        _, out = self.probe("codex", sentinel="")
        self.assertIn("FAIL  installed Codex requirements differ", out)

    def test_a_client_is_required(self):
        code, _ = self.probe(None, sentinel="")
        self.assertEqual(code, 64)


if __name__ == "__main__":
    unittest.main()
