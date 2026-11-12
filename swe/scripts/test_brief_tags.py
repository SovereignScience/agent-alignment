"""The tags that mark the parts of a review brief: one set, defined in one file."""
import pathlib
import re
import unittest

CLAUDE = pathlib.Path(__file__).resolve().parents[1] / ".claude"
DEFINED = set(re.findall(r"^- `<([a-z_]+)[ >]", (CLAUDE / "agents" / "code-reviewer.md").read_text(), re.M))
REVIEW_COMMANDS = ["swe-review", "swe-swarm-review", "swe-skeptic", "swe-security"]


class BriefTags(unittest.TestCase):
    def test_the_set_is_the_five_the_code_reviewer_defines(self):
        self.assertEqual(DEFINED, {"revisions", "request", "acceptance_criteria", "author_claims", "reference"})

    def test_no_agent_or_command_closes_a_tag_outside_the_set(self):
        for path in sorted(CLAUDE.glob("agents/*.md")) + sorted(CLAUDE.glob("commands/*.md")):
            used = set(re.findall(r"</([a-z_]+)>", path.read_text()))
            self.assertLessEqual(used, DEFINED, path.name)

    def test_every_review_command_writes_its_brief_in_the_tags(self):
        for name in REVIEW_COMMANDS:
            text = (CLAUDE / "commands" / (name + ".md")).read_text()
            for tag in ("revisions", "request", "acceptance_criteria", "author_claims"):
                self.assertIn("</%s>" % tag, text, "%s lacks %s" % (name, tag))


if __name__ == "__main__":
    unittest.main()
