"""check_drift.py against made-up modules, then against the real files."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check_drift.py")
TRACK = SCRIPT.parent.parent

MODULE = """# header
<sample>
TRUST: Earned slowly.

1. Hold boundaries as promises. A refusal is a commitment.

### Step 1: Stop the current trajectory

- Acknowledge growth. Update as the person changes.
- Am I agreeing because it is easier? (path of least resistance)
- A bullet with no name
</sample>

1. Numbered text in an example. It is outside the block.
"""
DERIVED = """TRUST: earned.
P1: Hold boundaries as promises.
1. STOP THE CURRENT
   TRAJECTORY
- Acknowledge growth.
- Am I agreeing because it is easier?
"""


class DriftCases(unittest.TestCase):
    def run_check(self, derived):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for name in ("INNER_COMMONS_CORE.md", "FLOURISHING_PROTOCOL.md",
                         "SKEPTIC_ARBITER.md", "REPAIR_PROTOCOL.md"):
                (root / name).write_text(MODULE)
            for name in ("COMPOSED_AGENT.md", "FOR_CLAUDE.md", "FOR_CHATGPT.md"):
                (root / name).write_text(DERIVED)
            (root / "FOR_API.md").write_text(derived)
            return subprocess.run([sys.executable, str(SCRIPT), folder],
                                  text=True, capture_output=True, timeout=20)

    def test_derived_files_with_every_item_pass(self):
        done = self.run_check(DERIVED)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_each_kind_of_missing_item_fails_and_is_named(self):
        cases = {
            "TRUST: earned.": "TRUST",
            "P1: Hold boundaries as promises.": "Hold boundaries as promises",
            "1. STOP THE CURRENT\n   TRAJECTORY": "Stop the current trajectory",
            "- Acknowledge growth.": "Acknowledge growth",
            "- Am I agreeing because it is easier?": "Am I agreeing because it is easier?",
        }
        for line, item in cases.items():
            with self.subTest(item=item):
                done = self.run_check(DERIVED.replace(line, ""))
                self.assertEqual(done.returncode, 1)
                self.assertIn('FOR_API.md lacks "%s"' % item, done.stderr)
                self.assertNotIn("COMPOSED_AGENT.md lacks", done.stderr)

    def test_a_defined_term_in_lower_case_does_not_count(self):
        done = self.run_check(DERIVED.replace("TRUST: earned.", "trust: earned."))
        self.assertEqual(done.returncode, 1)

    def test_a_term_inside_a_longer_term_does_not_count(self):
        done = self.run_check(DERIVED.replace("TRUST: earned.", "CIVIC TRUST: shared."))
        self.assertEqual(done.returncode, 1)
        self.assertIn('FOR_API.md lacks "TRUST"', done.stderr)

    def test_an_item_only_in_the_abbreviated_version_does_not_count(self):
        short = "\n# ── ABBREVIATED VERSION (short form) ──\n# - Acknowledge growth.\n"
        done = self.run_check(DERIVED.replace("- Acknowledge growth.\n", "") + short)
        self.assertEqual(done.returncode, 1)
        self.assertIn('FOR_API.md lacks "Acknowledge growth"', done.stderr)

    def test_a_module_with_no_tagged_block_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for name in ("INNER_COMMONS_CORE.md", "FLOURISHING_PROTOCOL.md",
                         "SKEPTIC_ARBITER.md", "REPAIR_PROTOCOL.md", "COMPOSED_AGENT.md",
                         "FOR_CLAUDE.md", "FOR_CHATGPT.md", "FOR_API.md"):
                (root / name).write_text("no block here\n")
            done = subprocess.run([sys.executable, str(SCRIPT), folder],
                                  text=True, capture_output=True, timeout=20)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no tagged block", done.stderr)

    def test_the_real_derived_files_carry_every_item(self):
        done = subprocess.run([sys.executable, str(SCRIPT), str(TRACK)],
                              text=True, capture_output=True, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
