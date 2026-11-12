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
WRAPPER = '#!/bin/sh\n# agent-safety push check\nexec python3 /etc/claude-code/hooks/pre-push "$@"\n'
KIT_COMMIT = "chore(agents): update the kit's agents and commands"


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
        for name in ("old-hook", "no-hook", "declined", "broken", "private", "foreign", "husky", "wrapped", "excluded"):
            self.git(self.work, "init", "-q", "-b", "main", name)
        # Listed in the owner's skip file: never touched, so it never asks about a push check.
        (self.home / ".config/agent-alignment").mkdir(parents=True)
        (self.home / ".config/agent-alignment/skip").write_bytes(b"excluded/\r\n")
        self.hook("old-hook").write_text('#!/usr/bin/env python3\n"""pre-push: show what is about to leave this machine, older."""\n')
        self.hook("wrapped").write_text(WRAPPER)
        self.hook("private").write_text("private hook\n")
        self.hook("foreign").write_text('#!/bin/sh\ngit lfs pre-push "$@"\n')
        self.git(self.work / "husky", "config", "core.hooksPath", ".husky/_")
        (self.work / "linked").symlink_to(self.work / "old-hook")
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
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()

    def project(self, name):
        """A repository with its own upstream whose tracked copy of the kit's reviewer is out of date."""
        root = self.work / name
        self.git(self.work, "init", "-q", "-b", "main", name)
        for key, value in (("user.name", "Test Owner"), ("user.email", "owner@example.com"),
                           ("core.hooksPath", ".no-hooks")):
            self.git(root, "config", key, value)
        (root / ".claude/agents").mkdir(parents=True)
        (root / ".claude/agents/code-reviewer.md").write_text("an old copy of the kit's reviewer\n")
        self.git(root, "add", ".claude")
        self.git(root, "commit", "-q", "-m", "add the reviewer")
        remote = pathlib.Path(self.tmp.name, name + ".git")
        self.git(self.tmp.name, "init", "-q", "--bare", str(remote))
        self.git(root, "remote", "add", "origin", str(remote))
        self.git(root, "push", "-q", "-u", "origin", "main")
        return root

    def hook(self, name):
        return self.work / name / ".git/hooks/pre-push"

    def run_it(self, answers, *args, skip=("--skip", "private"), cwd=None, **extra):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("SWE_WORKSPACE", None)
        env.update(extra)
        done = subprocess.run(["bash", str(self.kit / "swe/scripts/update_all.sh"), *skip, *args],
                              env=env, input=answers, capture_output=True, text=True, timeout=120, cwd=cwd)
        return done.returncode, done.stdout + done.stderr

    def test_a_project_that_links_into_a_skipped_one_never_writes_there(self):
        excluded = self.work / "excluded"
        (excluded / ".claude/agents").mkdir(parents=True)
        (excluded / ".claude/agents/code-reviewer.md").write_text("an old copy of the kit's reviewer\n")
        (excluded / ".lattice").mkdir()
        (excluded / ".lattice/config.json").write_text("{}")
        self.hook("excluded").write_text(WRAPPER)
        (self.hook("excluded").parent / "tells_check.py").write_text("excluded's own\n")
        for name in ("via-git", "via-hooks", "via-hook-file", "via-claude", "via-agents", "via-board"):
            self.git(self.work, "init", "-q", "-b", "main", name)
        shutil.rmtree(self.work / "via-git/.git")
        (self.work / "via-git/.git").symlink_to(excluded / ".git")
        shutil.rmtree(self.work / "via-hooks/.git/hooks")
        (self.work / "via-hooks/.git/hooks").symlink_to(excluded / ".git/hooks")
        self.hook("via-hook-file").write_text(WRAPPER)
        (self.hook("via-hook-file").parent / "tells_check.py").symlink_to(excluded / ".git/hooks/tells_check.py")
        (self.work / "via-claude/.claude").symlink_to(excluded / ".claude")
        (self.work / "via-agents/.claude").mkdir()
        (self.work / "via-agents/.claude/agents").symlink_to(excluded / ".claude/agents")
        (self.work / "via-board/.lattice").symlink_to(excluded / ".lattice")
        # git-new-workdir: a real .git whose refs, objects and config are the other project's.
        for key, value in (("user.name", "Test Owner"), ("user.email", "owner@example.com")):
            self.git(excluded, "config", key, value)
        self.git(excluded, "add", ".claude")
        self.git(excluded, "commit", "-q", "-m", "add the reviewer")
        workdir = self.work / "via-new-workdir/.git"
        workdir.mkdir(parents=True)
        for part in ("refs", "objects", "config", "logs"):
            (workdir / part).symlink_to(excluded / ".git" / part)
        (workdir / "HEAD").write_text("ref: refs/heads/main\n")
        self.git(workdir.parent, "reset", "-q", "--hard")
        self.git(self.work, "init", "-q", "-b", "main", "via-worktree")
        self.git(self.work / "via-worktree", "config", "core.worktree", str(excluded))
        self.git(self.work, "init", "-q", "-b", "main", "via-hard-link")
        (self.work / "via-hard-link/.claude/agents").mkdir(parents=True)
        os.link(excluded / ".claude/agents/code-reviewer.md", self.work / "via-hard-link/.claude/agents/code-reviewer.md")
        before = {p: p.read_bytes() for p in excluded.rglob("*") if p.is_file()}
        _, out = self.run_it("", "--yes")
        self.assertEqual({p: p.read_bytes() for p in excluded.rglob("*") if p.is_file()}, before, out)
        self.assertNotIn("board_update --apply in via-board", out)
        for path in (".git", ".git/hooks"):
            self.assertIn("note     %s is a link; this project is left alone" % path, out)
        self.assertRegex(out, r"== via-new-workdir\nnote     \.git/\w+ is a link; this project is left alone\n")
        self.assertIn("== via-worktree\nnote     Git keeps this project's repository or work tree elsewhere", out)
        for path, count in ((".claude/agents", 2), (".lattice", 1)):
            self.assertEqual(out.count("note     %s is a link or not a plain folder; left alone" % path), count, out)
        self.assertIn("note     the push hook or tells_check.py is a link (left alone)", out)

    def test_with_a_relative_workspace_a_tracked_copy_with_edits_is_kept(self):
        root = self.project("edited")
        (root / ".claude/agents/code-reviewer.md").write_text("a local edit\n")
        head = self.git(root, "rev-parse", "HEAD")
        _, out = self.run_it("", "--yes", cwd=self.home, SWE_WORKSPACE="work")
        self.assertEqual((root / ".claude/agents/code-reviewer.md").read_text(), "a local edit\n")
        self.assertEqual(self.git(root, "rev-parse", "HEAD"), head)
        self.assertIn("kept     .claude/agents/code-reviewer.md: it has uncommitted edits", out)

    def test_the_push_sends_no_tags_even_where_push_follow_tags_is_on(self):
        root = self.project("tagged")
        self.git(root, "tag", "-a", "-m", "not for the remote", "internal-note")
        self.git(root, "config", "push.followTags", "true")
        _, out = self.run_it("", "--yes", "--push")
        self.assertIn("pushed   main to origin", out)
        remote = str(pathlib.Path(self.tmp.name, "tagged.git"))
        self.assertEqual(self.git(self.tmp.name, "--git-dir", remote, "rev-parse", "main"), self.git(root, "rev-parse", "HEAD"))
        self.assertEqual(self.git(self.tmp.name, "--git-dir", remote, "tag"), "")

    def test_without_a_skip_list_or_with_a_name_that_matches_nothing_it_stops_before_any_project(self):
        skip = self.home / ".config/agent-alignment/skip"
        old_hook = self.hook("old-hook").read_text()
        skip.unlink()
        code, out = self.run_it("", "--yes", skip=())
        self.assertEqual(code, 1, out)
        self.assertIn("no %s: name the folders to leave out there" % skip, out)
        self.assertNotIn("== ", out)
        skip.write_bytes(b"  excluded/ \r\nprivat\n")
        code, out = self.run_it("", "--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("nothing in %s is named privat;" % self.work, out)
        self.assertNotIn("== ", out)
        self.assertEqual(self.hook("old-hook").read_text(), old_hook)
        skip.write_bytes(b"")
        code, out = self.run_it("", "--yes", skip=())
        self.assertIn("skip     nothing\n", out)
        self.assertIn("== private", out)

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
        self.assertNotIn("== linked", out)
        self.assertEqual(self.hook("foreign").read_text(), '#!/bin/sh\ngit lfs pre-push "$@"\n')
        self.assertEqual(list(self.hook("foreign").parent.glob("pre-push.*.bak")), [])
        self.assertIn("note     another tool's push hook is here (left alone)", out)
        self.assertFalse(self.hook("husky").exists())
        self.assertIn("(core.hooksPath); push check left alone", out)
        self.assertEqual(self.hook("wrapped").read_bytes(), kit_hook)
        self.assertEqual([p.read_text() for p in self.hook("wrapped").parent.glob("pre-push.*.bak")], [WRAPPER])
        self.assertIn("note     not committed: Git does not track them here", out)
        self.assertIn("machine  the installed rules, agents and commands match the kit", out)
        self.assertIn("stale    .claude/agents/code-reviewer.md", out)
        copy = (self.work / "old-hook/.claude/agents/code-reviewer.md").read_text()
        self.assertEqual(copy, (SWE / ".claude/agents/code-reviewer.md").read_text())
        self.assertNotIn(str(self.home), copy)
        self.assertNotIn("== excluded", out)
        self.assertIn("skip     private excluded\n", out)
        self.assertEqual((self.work / "old-hook/.claude/agents/their-own.md").read_text(), "an agent of this project\n")
        self.assertEqual([p.read_text() for p in (self.work / "old-hook/.claude/agents").glob("code-reviewer.md.*.bak")],
                         ["an old copy of the kit's reviewer\n"])

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

    def test_kit_copies_are_committed_and_pushed_only_where_nothing_else_waits(self):
        clean, ahead, staged, detached, merging, reverting, forked = (
            self.project(n) for n in ("clean", "ahead", "staged", "detached", "merging", "reverting", "forked"))
        # A fork set-up: pushes go to the owner's fork, not to the upstream the branch tracks.
        fork = pathlib.Path(self.tmp.name, "forked-fork.git")
        self.git(self.tmp.name, "init", "-q", "--bare", str(fork))
        self.git(forked, "remote", "add", "fork", str(fork))
        self.git(forked, "push", "-q", "fork", "main")
        self.git(forked, "config", "branch.main.pushRemote", "fork")
        # A revert in progress, which Git would let a commit end.
        self.git(reverting, "update-ref", "REVERT_HEAD", "HEAD")
        # Another branch with a commit its remote lacks, which push.default=matching would also send.
        self.git(clean, "checkout", "-q", "-b", "other")
        self.git(clean, "push", "-q", "origin", "other")
        (clean / "notes.txt").write_text("private\n")
        self.git(clean, "add", "notes.txt")
        self.git(clean, "commit", "-q", "-m", "private")
        self.git(clean, "checkout", "-q", "main")
        self.git(clean, "config", "push.default", "matching")
        (ahead / "notes.txt").write_text("work in progress\n")
        self.git(ahead, "add", "notes.txt")
        self.git(ahead, "commit", "-q", "-m", "work in progress")
        (staged / "notes.txt").write_text("staged by hand\n")
        self.git(staged, "add", "notes.txt")
        self.git(detached, "checkout", "-q", "--detach")
        # A merge in progress whose index equals HEAD.
        self.git(merging, "checkout", "-q", "-b", "side")
        self.git(merging, "commit", "-q", "--allow-empty", "-m", "side")
        self.git(merging, "checkout", "-q", "main")
        self.git(merging, "merge", "-q", "--no-ff", "--no-commit", "-s", "ours", "side")
        before = {root: self.git(root, "rev-parse", "HEAD") for root in (staged, detached, merging, reverting)}
        forked_remotes = {path: self.git(self.tmp.name, "--git-dir", str(path), "rev-parse", "main")
                          for path in (fork, pathlib.Path(self.tmp.name, "forked.git"))}
        _, out = self.run_it("", "--yes", "--push")
        for root in (clean, ahead):
            self.assertEqual(self.git(root, "log", "-1", "--format=%s"), KIT_COMMIT, out)
            self.assertEqual(self.git(root, "show", "--name-only", "--format=", "HEAD"), ".claude/agents/code-reviewer.md")
        self.assertEqual(self.git(clean, "rev-parse", "HEAD"), self.git(clean, "rev-parse", "origin/main"))
        remote = pathlib.Path(self.tmp.name, "clean.git")
        self.assertNotEqual(self.git(self.tmp.name, "--git-dir", str(remote), "rev-parse", "other"),
                            self.git(clean, "rev-parse", "other"))
        self.assertIn("pushed   main to origin", out)
        self.assertEqual(self.git(ahead, "rev-list", "--count", "origin/main..HEAD"), "2")
        self.assertIn("not pushed: main has 2 commits its upstream lacks", out)
        for root in (staged, detached, merging, reverting):
            self.assertEqual(self.git(root, "rev-parse", "HEAD"), before[root])
        self.assertIn("not committed: something else is already staged here", out)
        self.assertIn("not committed: HEAD is on no branch here", out)
        self.assertIn("in the middle of an operation here (MERGE_HEAD)", out)
        self.assertIn("in the middle of an operation here (REVERT_HEAD)", out)
        self.git(merging, "rev-parse", "-q", "--verify", "MERGE_HEAD")
        self.git(reverting, "rev-parse", "-q", "--verify", "REVERT_HEAD")
        self.assertEqual(self.git(forked, "log", "-1", "--format=%s"), KIT_COMMIT)
        for path, head in forked_remotes.items():
            self.assertEqual(self.git(self.tmp.name, "--git-dir", str(path), "rev-parse", "main"), head)
        self.assertIn("not pushed: pushes from main do not go to its upstream refs/remotes/origin/main", out)
        # An uncommitted edit to a tracked copy is left as it is.
        (clean / ".claude/agents/code-reviewer.md").write_text("a local edit\n")
        _, again = self.run_it("", "--yes", "--push", "--skip", "broken", "--skip", "merging", "--skip", "reverting")
        self.assertEqual((clean / ".claude/agents/code-reviewer.md").read_text(), "a local edit\n")
        self.assertIn("kept     .claude/agents/code-reviewer.md: it has uncommitted edits", again)
        self.assertNotIn("PROBLEM", again)


if __name__ == "__main__":
    unittest.main()
