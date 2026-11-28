"""board_context.py in a throwaway kit with two versions of the template."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "board_context.py"
GUIDE = "# Guide\n\n```bash\nlattice init\n```\n\nThe context:\n\n```markdown\n%s```\n\nAfter it.\n"
V1 = ("# <name>\n\n## Purpose\n\nOne board for <project>.\n\n## Conventions\n\n"
      "- Task branches are feature/<CODE>-<n>-<slug>, from <branch>.\n"
      "- A finding is blocking or optional.\n"
      "- Evidence goes on the task.\n")
V2 = V1.replace("- A finding is blocking or optional.\n", "- A finding is graded P0 to P3.\n") + (
    "- Candidates live in .worktrees/<CODE>-<n>-a and are cut from <branch>.\n")
NEXT_TO_FILLED = ("- Review at http://127.0.0.1:<port>\n  (started one way).\n"
                  "- The board is in <board directory>\n  (kept out of Git).\n")


def fill(text):
    for mark, value in (("<name>", "shop"), ("<project>", "shop"), ("<CODE>", "SHOP"), ("<branch>", "develop"),
                        ("<port>", "8803"), ("<board directory>", "/srv/shop")):
        text = text.replace(mark, value)
    return text


class BoardContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.kit = root / "kit"
        (self.kit / "swe" / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.kit / "swe" / "scripts" / "board_context.py")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.kit, check=True)
        for text in (V1, V2):
            self.commit_guide(text)
        self.project = root / "shop"
        (self.project / ".lattice").mkdir(parents=True)
        self.context = self.project / ".lattice" / "context.md"
        self.context.write_text(fill(V1).replace("One board for shop.\n", "One board for shop.\nIt covers the storefront.\n"))

    def commit_guide(self, text):
        (self.kit / "swe" / "LATTICE_ONBOARDING.md").write_text(GUIDE % text)
        subprocess.run(["git", "add", "-A"], cwd=self.kit, check=True)
        subprocess.run(["git", "-c", "user.name=Owner", "-c", "user.email=owner@example.com", "commit", "-q",
                        "-m", "guide"], cwd=self.kit, check=True)

    def run_it(self, *args):
        run = subprocess.run([sys.executable, str(self.kit / "swe" / "scripts" / "board_context.py"), *args,
                              str(self.project)], capture_output=True, text=True)
        return run.returncode, run.stdout + run.stderr

    def test_status_says_behind_and_writes_nothing(self):
        before = self.context.read_text()
        code, out = self.run_it("status")
        self.assertEqual(code, 1, out)
        self.assertIn("behind     shop", out)
        self.assertEqual(self.context.read_text(), before)

    def test_apply_merges_the_new_rules_keeps_the_projects_edits_and_fills_its_names(self):
        code, out = self.run_it("apply")
        self.assertEqual(code, 0, out)
        text = self.context.read_text()
        self.assertIn("- A finding is graded P0 to P3.\n", text)
        self.assertNotIn("blocking or optional", text)
        self.assertIn("It covers the storefront.\n", text)
        self.assertIn("- Candidates live in .worktrees/SHOP-<n>-a and are cut from develop.\n", text)
        self.assertNotIn("<CODE>", text)
        self.assertEqual(self.run_it("status"), (0, "unchanged  shop: the board context has every template rule\n"))

    def test_a_change_next_to_the_port_or_board_directory_merges(self):
        v3 = V2 + NEXT_TO_FILLED
        self.commit_guide(v3)
        self.context.write_text(fill(v3))
        self.commit_guide(v3.replace("(started one way)", "(started with board)").replace(
            "(kept out of Git)", "(kept out of source Git)"))
        code, out = self.run_it("apply")
        self.assertEqual(code, 0, out)
        text = self.context.read_text()
        self.assertIn("http://127.0.0.1:8803\n  (started with board).\n", text)
        self.assertIn("/srv/shop\n  (kept out of source Git).\n", text)

    def test_a_committed_change_to_a_placeholder_line_merges(self):
        self.context.write_text(fill(V2))
        self.commit_guide(V2.replace("<slug>, from <branch>.", "<slug>, from <branch>, one per task."))
        code, out = self.run_it("apply")
        self.assertEqual(code, 0, out)
        self.assertIn("- Task branches are feature/SHOP-<n>-<slug>, from develop, one per task.\n",
                      self.context.read_text())

    def test_a_collision_leaves_the_context_alone_and_writes_the_merge_beside_it(self):
        mine = self.context.read_text().replace("- A finding is blocking or optional.\n",
                                                "- A finding is blocking, optional or a question.\n")
        self.context.write_text(mine)
        code, out = self.run_it("apply")
        self.assertEqual(code, 2, out)
        self.assertIn("collision  shop", out)
        self.assertEqual(self.context.read_text(), mine)
        proposed = pathlib.Path(str(self.context) + ".proposed").read_text()
        self.assertIn("<<<<<<<", proposed)
        self.assertIn("a question", proposed)
        self.assertIn("graded P0 to P3", proposed)

    def test_status_on_a_collision_writes_no_file(self):
        self.context.write_text(self.context.read_text().replace("blocking or optional", "blocking or not"))
        self.assertEqual(self.run_it("status")[0], 2)
        self.assertFalse(pathlib.Path(str(self.context) + ".proposed").exists())

    def test_a_folder_with_no_board_is_refused(self):
        shutil.rmtree(self.project / ".lattice")
        code, out = self.run_it("status")
        self.assertEqual(code, 3, out)
        self.assertIn("no board context", out)


if __name__ == "__main__":
    unittest.main()
