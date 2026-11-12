"""adr.py against a throwaway repository, and against this one."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "adr.py"
REPO = SCRIPT.parents[2]
BODY = "\n# ADR-%s: %s\n\n## Context\nc\n\n## Decision\nd\n\n## Rejected options\nr\n\n## Consequences\nq\n"


class Adr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Owner")
        self.git("config", "user.email", "owner@example.com")
        (self.root / "src").mkdir()
        (self.root / "src" / "pay.py").write_text("x = 1\n")
        (self.root / "docs").mkdir()
        self.record("0001", "Pay through the ledger", "status: accepted\ndate: 2026-01-02\ndecision-makers: Owner\n"
                    "applies-to:\n  - src/pay*.py\n")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout

    def record(self, number, title, facts):
        path = self.root / "docs" / ("ADR-%s-x.md" % number)
        path.write_text("---\n" + facts + "---\n" + BODY % (number, title))

    def commit(self):
        self.adr("index", "--write")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "records")

    def adr(self, *args):
        run = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root, capture_output=True, text=True)
        return run.returncode, run.stdout + run.stderr

    def test_a_file_is_matched_to_the_records_that_govern_it(self):
        code, out = self.adr("for", "src/pay.py")
        self.assertEqual(code, 0, out)
        self.assertIn("ADR-0001  Pay through the ledger", out)
        self.assertNotIn("not yet binding", out)
        self.assertIn("No decision record applies", self.adr("for", "README.md")[1])

    def test_a_proposed_record_is_shown_as_not_yet_binding(self):
        self.record("0002", "Pay in batches", "status: proposed\ndate: 2026-02-03\napplies-to: [src/pay.py]\n")
        self.commit()
        self.assertIn("ADR-0002  Pay in batches (proposed, not yet binding)", self.adr("for", "src/pay.py")[1])

    def test_a_superseded_record_no_longer_governs_and_the_index_says_what_replaced_it(self):
        self.record("0001", "Pay through the ledger", "status: superseded\ndate: 2026-01-02\ndecision-makers: Owner\n"
                    "applies-to:\n  - src/pay*.py\n")
        self.record("0002", "Pay in batches", "status: accepted\ndate: 2026-02-03\ndecision-makers: Owner\n"
                    "supersedes: ADR-0001\napplies-to: [src/pay.py]\n")
        self.commit()
        out = self.adr("for", "src/pay.py")[1]
        self.assertIn("ADR-0002", out)
        self.assertNotIn("ADR-0001", out)
        self.assertIn("superseded by ADR-0002", (self.root / "docs" / "ADR-INDEX.md").read_text())
        self.assertEqual(self.adr("check")[0], 0)

    def test_a_reviewer_reads_the_records_as_they_stood_before_the_change(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.record("0001", "Pay through the ledger", "status: rejected\ndate: 2026-01-02\napplies-to: [src/pay.py]\n")
        self.commit()
        self.assertIn("No decision record applies", self.adr("for", "src/pay.py")[1])
        self.assertIn("ADR-0001", self.adr("for", "--rev", base, "src/pay.py")[1])

    def test_check_names_each_fault_in_a_record(self):
        faults = {
            "unknown key 'owner'": "status: accepted\ndate: 2026-01-02\ndecision-makers: Owner\nowner: me\napplies-to: [src/pay.py]\n",
            "matches no file": "status: proposed\ndate: 2026-01-02\napplies-to: [lib/*.py]\n",
            "names its decision-makers": "status: accepted\ndate: 2026-01-02\napplies-to: [src/pay.py]\n",
            "status must be one of": "status: done\ndate: 2026-01-02\napplies-to: [src/pay.py]\n",
            "date must be a date": "status: proposed\ndate: January\napplies-to: [src/pay.py]\n",
            "not a record here": "status: proposed\ndate: 2026-01-02\nsupersedes: ADR-0009\napplies-to: [src/pay.py]\n",
            "no accepted record supersedes it": "status: superseded\ndate: 2026-01-02\napplies-to: [src/pay.py]\n",
            "applies-to names at least one glob": "status: proposed\ndate: 2026-01-02\n",
        }
        for message, facts in faults.items():
            self.record("0001", "Pay through the ledger", facts)
            self.commit()
            code, out = self.adr("check")
            self.assertEqual(code, 1, message)
            self.assertIn(message, out)

    def test_check_fails_on_a_stale_index_and_on_an_old_record_left_accepted(self):
        self.record("0002", "Pay in batches", "status: accepted\ndate: 2026-02-03\ndecision-makers: Owner\n"
                    "supersedes: ADR-0001\napplies-to: [src/pay.py]\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "no index")
        code, out = self.adr("check")
        self.assertEqual(code, 1)
        self.assertIn("ADR-INDEX.md is out of date", out)
        self.assertIn("status must be superseded", out)

    def test_check_warns_when_the_review_date_has_passed(self):
        self.record("0001", "Pay through the ledger", "status: accepted\ndate: 2026-01-02\ndecision-makers: Owner\n"
                    "applies-to: [src/pay.py]\nreview-by: 2026-02-01\n")
        self.commit()
        code, out = self.adr("check")
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)
        self.assertIn("review-by 2026-02-01 has passed", out)

    def test_this_repository_passes_its_own_check(self):
        run = subprocess.run([sys.executable, str(SCRIPT), "check"], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
