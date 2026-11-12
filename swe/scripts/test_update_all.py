"""update_all.sh against a made-up workspace of repositories, with stand-ins for the installer and the board update."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SWE = HERE.parent
STATUS = '#!/usr/bin/env bash\n[ "$1 $2" = "status --exit-code" ] || exit 64\nexit "$(cat "$HOME/machine")"\n'
BOARD = '#!/usr/bin/env bash\necho "board_update $* in $(basename "$PWD")"\n[ "$(basename "$PWD")" != broken ] || exit 1\n'


class UpdateAll(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name, "home")
        self.work = self.home / "work"
        kit = self.work / "kit"
        for folder in ("swe/scripts", "swe/.claude/scripts", "swe/.claude/agents"):
            (kit / folder).mkdir(parents=True)
        for name in ("update_all.sh", "kit_files.sh"):
            shutil.copy(HERE / name, kit / "swe/scripts" / name)
        shutil.copy(SWE / ".claude/agents/code-reviewer.md", kit / "swe/.claude/agents/code-reviewer.md")
        (kit / "swe/scripts/switch_rules.sh").write_text(STATUS)
        (kit / "swe/scripts/board_update.sh").write_text(BOARD)
        for name in ("pre-push", "tells_check.py"):
            shutil.copy(SWE / ".claude/scripts" / name, kit / "swe/.claude/scripts" / name)
        self.git(kit, "init", "-q", "-b", "main")
        (self.home / "machine").write_text("0")
        for name in ("old-hook", "no-hook", "declined", "broken", "private"):
            self.git(self.work, "init", "-q", "-b", "main", name)
        self.hook("old-hook").write_text("old hook\n")
        self.hook("private").write_text("private hook\n")
        for name in ("old-hook", "broken"):
            (self.work / name / ".lattice").mkdir()
            (self.work / name / ".lattice/config.json").write_text("{}")
        (self.work / "not-a-repo").mkdir()
        own = self.work / "old-hook/.claude/agents"
        own.mkdir(parents=True)
        (own / "code-reviewer.md").write_text("an old copy of the kit's reviewer\n")
        (own / "their-own.md").write_text("an agent of this project\n")
        self.kit = kit

    def git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    def hook(self, name):
        return self.work / name / ".git/hooks/pre-push"

    def run_it(self, answers, *args):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("SWE_WORKSPACE", None)
        done = subprocess.run(["bash", str(self.kit / "swe/scripts/update_all.sh"), "--skip", "private", *args],
                              env=env, input=answers, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def test_each_project_gets_the_push_check_and_its_board_brought_up_to_date(self):
        code, out = self.run_it("y\nn\nn\ny\n")
        self.assertEqual(code, 1, out)
        kit_hook = (SWE / ".claude/scripts/pre-push").read_bytes()
        self.assertEqual(self.hook("old-hook").read_bytes(), kit_hook)
        self.assertEqual(len(list(self.hook("old-hook").parent.glob("pre-push.*.bak"))), 1)
        self.assertEqual(self.hook("broken").read_bytes(), kit_hook)
        self.assertFalse(self.hook("declined").exists())
        self.assertFalse(self.hook("no-hook").exists())
        self.assertEqual(self.hook("private").read_text(), "private hook\n")
        self.assertIn("board_update --apply in old-hook", out)
        self.assertIn("board_update --apply in broken", out)
        self.assertIn("PROBLEM  the board was not brought up to date", out)
        self.assertIn("1 project(s) could not be brought up to date", out)
        self.assertNotIn("== kit", out)
        self.assertNotIn("== private", out)
        self.assertNotIn("== not-a-repo", out)
        self.assertIn("machine  the installed rules, agents and commands match the kit", out)
        self.assertIn("stale    .claude/agents/code-reviewer.md", out)
        lines = (SWE / ".claude/agents/code-reviewer.md").read_text().split("\n")
        end = lines.index("---", 1)
        note = ("The kit's files that this names (the five protocols, CRAFT.md, and anything under scripts/ or tools/) "
                "are in %s, whichever project you are in." % (self.kit / "swe"))
        self.assertEqual((self.work / "old-hook/.claude/agents/code-reviewer.md").read_text(),
                         "\n".join(lines[:end + 1] + ["", note] + lines[end + 1:]))
        self.assertEqual((self.work / "old-hook/.claude/agents/their-own.md").read_text(), "an agent of this project\n")

    def test_a_second_run_changes_nothing_and_a_machine_behind_the_kit_is_named(self):
        (self.work / "broken").rename(self.work / "mended")
        self.run_it("y\ny\ny\ny\n")
        (self.home / "machine").write_text("3")
        code, out = self.run_it("", "--yes")
        self.assertEqual(code, 0, out)
        self.assertNotIn("updated", out)
        self.assertNotIn("installed", out)
        self.assertNotIn("stale", out)
        self.assertIn("DONE: every project in %s is up to date" % self.work, out)
        self.assertIn("machine  BEHIND: run bash", out)


if __name__ == "__main__":
    unittest.main()
