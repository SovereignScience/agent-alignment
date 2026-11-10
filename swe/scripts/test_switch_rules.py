"""switch_rules.sh in a copy of this track, with a made-up home, /etc and sudo. Nothing real is touched."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from test_install_isolation import PROFILE

SWE = pathlib.Path(__file__).resolve().parent.parent
FAKE_SUDO = '''#!/usr/bin/env bash
args=()
while [ "$#" -gt 0 ]; do
    case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac
done
exec "${args[@]}"
'''
FILLED = "- Never read, run, update or audit anything in ~/private.\n"
PLACEHOLDER = "- Never read, run, update or audit anything in <folders kept off limits>.\n"


class SwitchRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.home = root / "home"
        (self.home / "projects").mkdir(parents=True)
        (self.home / ".claude").mkdir()
        self.etc = root / "etc"
        (self.etc / "claude-code").mkdir(parents=True)
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "sudo").write_text(FAKE_SUDO)
        (self.bin / "sudo").chmod(0o755)

        # A repository of its own, so the hooks folder and board context are made up too.
        self.repo = root / "repo"
        shutil.copytree(SWE, self.repo / "swe", ignore=shutil.ignore_patterns("__pycache__"))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Owner")
        self.git("config", "user.email", "owner@example.com")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.template = self.repo / "swe/user/CLAUDE.md"
        self.assertIn(PLACEHOLDER, self.template.read_text())
        self.rules = self.home / ".claude/CLAUDE.md"
        self.rules.write_text(self.template.read_text().replace(PLACEHOLDER, FILLED))
        self.hook = self.repo / ".git/hooks/pre-push"
        self.hook.write_text("old hook\n")
        self.context = self.repo / ".lattice/context.md"
        self.context.parent.mkdir()
        self.context.write_text("old context\n")
        self.template.write_text(self.template.read_text() + "- A rule this checkout adds.\n")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def switch(self, *args):
        env = dict(os.environ, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                   SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                   PATH="%s:%s" % (self.bin, os.environ["PATH"]))
        run = subprocess.run(["bash", str(self.repo / "swe/scripts/switch_rules.sh"), *args], env=env,
                             input="y\ny\n", capture_output=True, text=True, timeout=180, cwd=self.repo)
        return run.returncode, run.stdout + run.stderr

    def snapshots(self):
        store = self.home / ".config/agent-alignment/snapshots"
        return sorted(store.iterdir()) if store.exists() else []

    def test_status_writes_nothing(self):
        before = self.rules.read_text()
        code, out = self.switch("status")
        self.assertEqual(code, 0, out)
        self.assertIn("would merge template changes into", out)
        self.assertIn("would update", out)
        self.assertEqual(self.snapshots(), [])
        self.assertEqual(self.rules.read_text(), before)
        self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())

    def test_apply_installs_and_revert_puts_everything_back(self):
        before = self.rules.read_text()
        new_context = self.repo / "new-context.md"
        new_context.write_text("new context\n")
        code, out = self.switch("apply", "--context", str(new_context))
        self.assertEqual(code, 0, out)
        guard = self.etc / "claude-code/hooks/guard_outward.py"
        self.assertTrue(guard.exists(), out)
        merged = self.rules.read_text()
        self.assertIn(FILLED, merged)
        self.assertIn("- A rule this checkout adds.\n", merged)
        self.assertEqual(self.hook.read_bytes(), (self.repo / "swe/.claude/scripts/pre-push").read_bytes())
        self.assertEqual(self.context.read_text(), "new context\n")
        self.assertEqual(len(self.snapshots()), 1)

        code, out = self.switch("revert")
        self.assertEqual(code, 0, out)
        self.assertFalse(guard.exists(), out)
        self.assertFalse((self.etc / "claude-code/managed-settings.json").exists(), out)
        self.assertEqual(self.rules.read_text(), before)
        self.assertEqual(self.hook.read_text(), "old hook\n")
        self.assertEqual(self.context.read_text(), "old context\n")
        self.assertFalse((self.repo / ".git/hooks/tells_check.py").exists())

    def test_codex_gets_the_profile_and_the_same_rules_and_both_go_back(self):
        codex = self.home / ".codex"
        (codex / "attachments").mkdir(parents=True)
        (codex / "skills/openai-docs").mkdir(parents=True)
        (codex / "config.toml").write_text(PROFILE)
        agents = codex / "AGENTS.md"
        agents.write_text(self.rules.read_text())
        before = agents.read_text()
        code, out = self.switch("apply")
        self.assertEqual(code, 0, out)
        requirements = self.etc / "codex/requirements.toml"
        self.assertTrue(requirements.exists(), out)
        self.assertIn(FILLED, agents.read_text())
        self.assertIn("- A rule this checkout adds.\n", agents.read_text())
        self.assertNotEqual((codex / "config.toml").read_text(), PROFILE)
        code, out = self.switch("revert")
        self.assertEqual(code, 0, out)
        self.assertFalse(requirements.exists(), out)
        self.assertEqual(agents.read_text(), before)
        self.assertEqual((codex / "config.toml").read_text(), PROFILE)

    def test_status_warns_when_codex_would_drop_instructions(self):
        codex = self.home / ".codex"
        codex.mkdir()
        (codex / "AGENTS.md").write_text("- a rule\n" * 4000)
        code, out = self.switch("status")
        self.assertEqual(code, 0, out)
        self.assertIn("over its limit of 32768", out)
        (codex / "config.toml").write_text("project_doc_max_bytes = 65536\n")
        code, out = self.switch("status")
        self.assertEqual(code, 0, out)
        self.assertNotIn("over its limit", out)

    def test_a_colliding_template_change_stops_before_anything_is_written(self):
        self.template.write_text(self.template.read_text().replace(PLACEHOLDER, "- A reworded rule.\n"))
        before = self.rules.read_text()
        code, out = self.switch("status")
        self.assertEqual(code, 0, out)
        self.assertIn("collision", out)
        self.assertNotIn("would merge template changes", out)
        code, out = self.switch("apply")
        self.assertNotEqual(code, 0)
        self.assertIn("collision", out)
        self.assertIn("nothing was written", out)
        self.assertEqual(self.rules.read_text(), before)
        self.assertEqual(self.snapshots(), [])
        self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())

    def test_revert_needs_a_snapshot_and_bad_arguments_are_refused(self):
        code, out = self.switch("revert")
        self.assertNotEqual(code, 0)
        self.assertIn("no snapshot", out)
        for args in ((), ("apply", "--context"), ("apply", "--context", "missing.md"), ("install",)):
            with self.subTest(args=args):
                code, _ = self.switch(*args)
                self.assertNotEqual(code, 0)
        self.assertEqual(self.snapshots(), [])


if __name__ == "__main__":
    unittest.main()
