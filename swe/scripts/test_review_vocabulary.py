"""One way to grade a review finding: P0 to P3, defined in one file."""
import pathlib
import re
import unittest

SWE = pathlib.Path(__file__).resolve().parents[1]
FILES = [SWE / "SKEPTIC_ARBITER.md", SWE / "LATTICE_ONBOARDING.md", SWE / "user" / "CLAUDE.md"] + [
    SWE / ".claude" / kind / (name + ".md") for kind, name in [
        ("agents", "code-reviewer"), ("agents", "code-arbiter"), ("agents", "security-reviewer"),
        ("agents", "dependency-auditor"), ("agents", "perf-auditor"),
        ("commands", "swe-review"), ("commands", "swe-security"), ("commands", "swe-deps"),
        ("commands", "swe-compare"), ("commands", "swe-swarm-review"), ("commands", "swe-skeptic")]]
OLD = re.compile(r"\[(CRITICAL|HIGH|MEDIUM|MED|LOW|INFO)\]|(?<![-\w])(BLOCKER|MAJOR|MINOR|CRITICAL)\b"
                 r"|(?i:blocking or optional|blocking findings?|optional findings?)")


class ReviewVocabulary(unittest.TestCase):
    def test_no_reviewer_file_uses_an_older_scale(self):
        for path in FILES:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                self.assertIsNone(OLD.search(line), "%s:%d: %s" % (path.name, number, line.strip()))

    def test_the_grades_are_defined_in_one_file(self):
        holders = [path.name for path in FILES if re.search(r"^\s*- P0: ", path.read_text(), re.M)]
        self.assertEqual(holders, ["code-reviewer.md"])


if __name__ == "__main__":
    unittest.main()
