"""check_drift.sh against a copy of the kit's layout."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check_drift.sh")
FILES = ("SWE_CORE.md", "TESTING_PROTOCOL.md", "PERFORMANCE_PROTOCOL.md", "SECURITY_PROTOCOL.md",
         "SKEPTIC_ARBITER.md", "README.md", "CLAUDE.md")


class CheckDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.swe = pathlib.Path(self.tmp.name, "swe")
        (self.swe / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.swe / "scripts/check_drift.sh")
        for name in FILES:
            (self.swe / name).write_text(name + "\n")

    def run_it(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.tmp.name)
        done = subprocess.run(["bash", str(self.swe / "scripts/check_drift.sh")], cwd="/", env=env,
                              capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def test_it_reads_its_own_folder_wherever_the_session_was_opened(self):
        code, out = self.run_it()
        self.assertEqual(code, 0, out)
        self.assertNotIn("MISSING-FILE", out)

    def test_a_missing_protocol_fails_the_check(self):
        (self.swe / "SECURITY_PROTOCOL.md").unlink()
        code, out = self.run_it()
        self.assertEqual(code, 1, out)
        self.assertIn("1 file(s) missing", out)


if __name__ == "__main__":
    unittest.main()
