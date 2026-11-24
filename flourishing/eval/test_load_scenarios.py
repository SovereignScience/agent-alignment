"""Parse synthetic scenario files; no model is called."""
import pathlib
import tempfile
import unittest

import load_scenarios

MULTI_TURN = """# Scenario 90: multi-turn

## Earlier turns
> User: First question,
> on two lines.
> Assistant: First answer.

## User input
> Second question.

## Failure modes to catch
- Not a criterion.

## Pass criteria
- The reply does **not** do one thing
  that wraps onto a second line.
- The reply does another thing.
"""

SINGLE_TURN = """# Scenario 91: single turn

## User input
> Only question.

## Pass criteria
- The reply answers it.
"""


class ParseCases(unittest.TestCase):
    def parse(self, name, text):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder, name)
            path.write_text(text, encoding="utf-8")
            return load_scenarios.parse(path)

    def test_multi_turn(self):
        test = self.parse("90_multi.md", MULTI_TURN)
        self.assertEqual(test["description"], "90_multi")
        self.assertEqual(test["vars"]["messages"], [
            {"role": "user", "content": "First question,\non two lines."},
            {"role": "assistant", "content": "First answer."},
            {"role": "user", "content": "Second question."},
        ])
        self.assertEqual([a["type"] for a in test["assert"]], ["llm-rubric", "llm-rubric"])
        self.assertEqual([a["metric"] for a in test["assert"]], ["90_multi.1", "90_multi.2"])
        self.assertTrue(test["assert"][0]["value"].startswith(
            "The reply does **not** do one thing that wraps onto a second line.\n"))
        self.assertIn("Assistant: First answer.", test["assert"][0]["value"])

    def test_single_turn(self):
        test = self.parse("91_single.md", SINGLE_TURN)
        self.assertEqual(test["vars"]["messages"], [{"role": "user", "content": "Only question."}])
        self.assertEqual(len(test["assert"]), 1)

    def test_missing_user_input_names_the_file(self):
        text = SINGLE_TURN.replace("## User input\n> Only question.\n", "")
        with self.assertRaisesRegex(ValueError, r"^92_no_input\.md: .*User input"):
            self.parse("92_no_input.md", text)

    def test_missing_pass_criterion_names_the_file(self):
        text = SINGLE_TURN.replace("- The reply answers it.\n", "")
        with self.assertRaisesRegex(ValueError, r"^93_no_criteria\.md: .*Pass criteria"):
            self.parse("93_no_criteria.md", text)

    def test_unindented_continuation_of_a_criterion_names_the_file(self):
        text = SINGLE_TURN.replace("- The reply answers it.\n", "- The reply does **not**\nclaim it.\n")
        with self.assertRaisesRegex(ValueError, r"^94_cut\.md: .*Pass criteria"):
            self.parse("94_cut.md", text)

    def test_checked_in_scenarios_all_load(self):
        files = sorted(load_scenarios.SCENARIOS.glob("[0-9][0-9]_*.md"))
        self.assertEqual([test["description"] for test in load_scenarios.generate_tests()],
                         [path.stem for path in files])


if __name__ == "__main__":
    unittest.main()
