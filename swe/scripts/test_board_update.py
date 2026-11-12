"""board_update.sh against two checkouts of one board, a bare remote and the real lattice command."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).parent
BASH = shutil.which("bash")


@unittest.skipUnless(shutil.which("lattice"), "lattice is not installed")
class BoardUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = pathlib.Path(self.tmp.name, "home")
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(HOME=str(home), LATTICE_NO_UPDATE_CHECK="1")
        self.env.pop("LATTICE_ROOT", None)
        self.remote = pathlib.Path(self.tmp.name, "board.git")
        self.run_in(self.tmp.name, "git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.here, self.there = self.project("one"), self.project("two")
        for repo in (self.here, self.there):
            self.script("board_setup.sh", "--actor", "human:owner", "--remote", str(self.remote), cwd=repo)

    def project(self, parent):
        repo = pathlib.Path(self.tmp.name, parent, "demo-project")
        repo.mkdir(parents=True)
        self.run_in(repo, "git", "init", "-q", "-b", "main")
        (repo / "README.md").write_text("demo\n")
        self.run_in(repo, "git", "add", "README.md")
        self.run_in(repo, "git", "commit", "-q", "-m", "add readme")
        return repo

    def run_in(self, cwd, *command, check=True):
        run = subprocess.run(command, cwd=cwd, env=dict(self.env, LATTICE_ROOT=str(cwd)), capture_output=True,
                             text=True, timeout=120)
        if check and run.returncode:
            self.fail("%s: %s" % (" ".join(command), run.stdout + run.stderr))
        return run.returncode, run.stdout + run.stderr

    def script(self, name, *args, cwd, check=True):
        return self.run_in(cwd, BASH, str(HERE / name), *args, check=check)

    def head(self, where):
        return self.run_in(where, "git", "rev-parse", "HEAD" if where != self.remote else "main")[1].strip()

    def task(self, repo, title):
        self.run_in(repo, "lattice", "create", title, "--actor", "human:owner")

    def test_the_fixture_ignores_inherited_git_configuration(self):
        inherited = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.quotePath", "GIT_CONFIG_VALUE_0": "false"}
        with mock.patch.dict(os.environ, inherited):
            fixture = BoardUpdate()
            self.addCleanup(fixture.doCleanups)
            fixture.setUp()
            code, out = fixture.run_in(fixture.here, "git", "config", "--default", "fixture-default", "--get", "core.quotePath")
            self.assertEqual(out.strip(), "fixture-default")
            fixture.task(fixture.here, "isolated configuration")
            code, out = fixture.script("board_update.sh", "--apply", cwd=fixture.here)
            self.assertEqual(code, 0, out)

    def test_without_apply_it_says_what_is_behind_and_changes_no_file(self):
        self.task(self.here, "first")
        before = self.head(self.here / ".lattice")
        code, out = self.script("board_update.sh", cwd=self.here)
        self.assertEqual(code, 0, out)
        self.assertIn("unchanged  demo-project", out)
        self.assertRegex(out, r"to commit  [1-9]\d* board file")
        self.assertIn("to push    0 commit(s)", out)
        self.assertIn("healthy", out)
        self.assertEqual(self.head(self.here / ".lattice"), before)
        self.assertEqual(self.head(self.remote), before)

    def test_one_sides_work_reaches_the_remote_and_then_the_other_side(self):
        self.task(self.here, "first")
        code, out = self.script("board_update.sh", "--apply", cwd=self.here)
        self.assertEqual(code, 0, out)
        self.assertIn("DONE: the board is in step with its remote", out)
        self.assertEqual(self.head(self.remote), self.head(self.here / ".lattice"))
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.assertEqual(self.head(self.there / ".lattice"), self.head(self.remote))
        self.assertIn("first", self.run_in(self.there, "lattice", "show", "DP-1")[1])

    def test_two_sides_that_wrote_the_same_task_are_merged_and_nothing_is_lost(self):
        self.task(self.here, "first")
        self.script("board_update.sh", "--apply", cwd=self.here)
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.run_in(self.here, "lattice", "comment", "DP-1", "said here", "--actor", "human:owner")
        self.run_in(self.there, "lattice", "comment", "DP-1", "said there", "--actor", "human:owner")
        self.script("board_update.sh", "--apply", cwd=self.here)
        code, out = self.script("board_update.sh", "--apply", cwd=self.there)
        self.assertEqual(code, 0, out)
        self.script("board_update.sh", "--apply", cwd=self.here)
        for repo in (self.here, self.there):
            comments = self.run_in(repo, "lattice", "comments", "DP-1", "--json")[1]
            self.assertIn("said here", comments)
            self.assertIn("said there", comments)
            self.assertEqual(self.head(repo / ".lattice"), self.head(self.remote))
            self.assertEqual(self.run_in(repo / ".lattice", "git", "status", "--porcelain")[1], "")
        self.assertIn("merge the remote board", self.run_in(self.there / ".lattice", "git", "log", "--format=%s")[1])

    def test_two_sides_that_each_made_a_task_are_not_merged(self):
        self.task(self.here, "made here")
        self.task(self.there, "made there")
        self.script("board_update.sh", "--apply", cwd=self.here)
        pushed = self.head(self.remote)
        code, out = self.script("board_update.sh", "--apply", cwd=self.there, check=False)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"changed on both sides; nothing was merged or pushed")
        self.assertEqual(self.head(self.remote), pushed)
        board = self.there / ".lattice"
        self.assertEqual(self.run_in(board, "git", "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)[0], 1)
        self.assertEqual(self.run_in(board, "git", "status", "--porcelain")[1], "")
        self.assertIn("made there", self.run_in(self.there, "lattice", "show", "DP-1")[1])

    def conflicted(self, change_here, said):
        self.task(self.here, "first")
        self.script("board_update.sh", "--apply", cwd=self.here)
        self.script("board_update.sh", "--apply", cwd=self.there)
        change_here()
        self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.run_in(self.there, "lattice", "comment", "DP-1", "said there", "--actor", "human:owner")
        pushed = self.head(self.remote)
        code, out = self.script("board_update.sh", "--apply", cwd=self.there, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn(said, out)
        self.assertIn("nothing was merged or pushed", out)
        board = self.there / ".lattice"
        self.assertEqual(self.run_in(board, "git", "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)[0], 1)
        self.assertEqual(self.run_in(board, "git", "status", "--porcelain")[1], "")
        self.assertEqual(self.head(self.remote), pushed)

    def test_a_task_archived_on_one_side_and_changed_on_the_other_stops_with_the_merge_undone(self):
        self.conflicted(lambda: self.run_in(self.here, "lattice", "archive", "DP-1", "--actor", "human:owner"),
                        "changed on both sides")

    def test_a_file_deleted_on_one_side_and_changed_on_the_other_stops_with_the_merge_undone(self):
        def delete():
            log = next((self.here / ".lattice/events").glob("task_*.jsonl")).name
            self.run_in(self.here / ".lattice", "git", "rm", "-q", "events/" + log)
            self.run_in(self.here / ".lattice", "git", "commit", "-q", "-m", "drop the log")
        self.conflicted(delete, "was deleted on one side and changed on the other")

    def test_an_error_in_the_context_update_stops_before_any_commit(self):
        (self.here / ".lattice/context.md").unlink()
        before = self.head(self.here / ".lattice")
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn("board_context.py failed (exit 3)", out)
        self.assertEqual(self.head(self.here / ".lattice"), before)

    def test_a_board_that_holds_a_link_is_left_alone(self):
        elsewhere = pathlib.Path(self.tmp.name, "elsewhere.md")
        elsewhere.write_text("another board's context\n")
        context = self.here / ".lattice/context.md"
        before = self.head(self.here / ".lattice")
        for make in (context.symlink_to, lambda target: os.link(target, context)):
            context.unlink()
            make(elsewhere)
            code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
            self.assertEqual(code, 1, out)
            self.assertIn(".lattice/context.md is a link; nothing was done", out)
            self.assertEqual(elsewhere.read_text(), "another board's context\n")
            self.assertEqual(self.head(self.here / ".lattice"), before)

    def test_a_board_whose_git_files_lead_elsewhere_is_left_alone(self):
        git = self.here / ".lattice/.git"
        before = self.head(self.here / ".lattice")
        objects = pathlib.Path(self.tmp.name, "objects")
        shutil.move(git / "objects", objects)
        (git / "objects").symlink_to(objects)
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn(".lattice/.git/objects is a link; nothing was done", out)
        (git / "objects").unlink()
        shutil.move(objects, git / "objects")
        (git / "commondir").write_text(str(self.remote) + "\n")
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn("Git finds the repository or work tree of .lattice elsewhere; nothing was done", out)
        (git / "commondir").unlink()
        self.assertEqual(self.head(self.here / ".lattice"), before)
        self.assertEqual(self.head(self.remote), before)

    def test_a_project_without_a_board_is_sent_to_the_setup_command(self):
        bare = self.project("three")
        code, out = self.script("board_update.sh", "--apply", cwd=bare, check=False)
        self.assertEqual(code, 1)
        self.assertIn("board_setup.sh makes one", out)

    def test_git_redirections_are_refused_before_git_runs(self):
        other_git = self.there / ".lattice/.git"
        index = (other_git / "index").read_bytes()
        objects = set((other_git / "objects").rglob("*"))
        trace = pathlib.Path(self.tmp.name, "outside-trace")
        trace.write_text("keep this trace\n")
        self.task(self.here, "first")
        for name, path in (("GIT_INDEX_FILE", other_git / "index"),
                           ("GIT_OBJECT_DIRECTORY", other_git / "objects"),
                           ("GIT_TRACE", trace), ("GIT_TRACE2_EVENT", trace)):
            self.env[name] = str(path)
            try:
                code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
            finally:
                del self.env[name]
            self.assertEqual(code, 1, out)
            self.assertIn(name + " is set", out)
            self.assertEqual((other_git / "index").read_bytes(), index)
            self.assertEqual(set((other_git / "objects").rglob("*")), objects)
            self.assertEqual(trace.read_text(), "keep this trace\n")
        bin_dir = pathlib.Path(self.tmp.name, "bin")
        bin_dir.mkdir()
        marker = bin_dir / "git-was-called"
        git = bin_dir / "git"
        git.write_text('#!/bin/sh\nprintf called > "$PROBE_MARKER"\nexit 91\n')
        git.chmod(0o755)
        self.env.update(PATH=str(bin_dir) + os.pathsep + self.env["PATH"], PROBE_MARKER=str(marker))
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                     "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS",
                     "GIT_CONFIG_GLOBAL", "GIT_NAMESPACE", "GIT_TRACE", "GIT_TRACE2_EVENT"):
            for value in (str(self.there / ".lattice/.git"), ""):
                with self.subTest(name=name, empty=not value):
                    self.env[name] = value
                    try:
                        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
                    finally:
                        del self.env[name]
                    self.assertEqual(code, 1, out)
                    self.assertIn(name + " is set", out)
                    if value:
                        self.assertNotIn(value, out)
                    self.assertFalse(marker.exists())

    def test_an_incoming_link_stops_before_a_fast_forward(self):
        victim = pathlib.Path(self.tmp.name, "victim")
        victim.write_text("outside board\n")
        link = self.there / ".lattice/notes/remote-link"
        link.parent.mkdir(exist_ok=True)
        link.symlink_to(victim)
        self.run_in(self.there / ".lattice", "git", "add", "--", "notes/remote-link")
        self.run_in(self.there / ".lattice", "git", "commit", "-q", "-m", "add fixture link")
        self.run_in(self.there / ".lattice", "git", "push", "-q", "origin", "main")
        before, pushed = self.head(self.here / ".lattice"), self.head(self.remote)
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn("the remote board holds a symbolic link", out)
        self.assertEqual(self.head(self.here / ".lattice"), before)
        self.assertEqual(self.head(self.remote), pushed)
        self.assertFalse((self.here / ".lattice/notes/remote-link").is_symlink())
        self.assertEqual(victim.read_text(), "outside board\n")

    def test_configured_trace_targets_are_refused_without_opening_them(self):
        config = pathlib.Path(self.env["HOME"], ".gitconfig")
        original = config.read_text()
        victim = pathlib.Path(self.tmp.name, "outside-trace")
        victim.write_text("keep this trace\n")
        included = pathlib.Path(self.tmp.name, "trace-config")
        for target in ("normalTarget", "perfTarget", "eventTarget"):
            trace = "\n[trace2]\n\t%s = %s\n" % (target, victim)
            included.write_text(trace)
            conditional = '\n[includeIf "gitdir:%s"]\n\tpath = %s\n' % (
                self.here / ".lattice/.git", included)
            for settings in (trace, conditional):
                with self.subTest(target=target, conditional=settings == conditional):
                    config.write_text(original + settings)
                    try:
                        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
                    finally:
                        config.write_text(original)
                    self.assertEqual(code, 1, out)
                    self.assertIn("trace2." + target.lower() + " is configured", out)
                    self.assertNotIn(str(victim), out)
                    self.assertEqual(victim.read_text(), "keep this trace\n")

    def test_an_unreadable_git_configuration_stops_without_printing_it(self):
        config = pathlib.Path(self.env["HOME"], ".gitconfig")
        original = config.read_text()
        config.write_text(original + "\n[do-not-print-this-config-content\n")
        try:
            code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        finally:
            config.write_text(original)
        self.assertEqual(code, 1, out)
        self.assertIn("Git tracing configuration could not be read", out)
        self.assertNotIn("do-not-print-this-config-content", out)

    def test_an_unreadable_remote_tree_stops_before_a_merge(self):
        self.task(self.here, "first")
        before = self.head(self.remote)
        bin_dir = pathlib.Path(self.tmp.name, "bin")
        bin_dir.mkdir()
        git = bin_dir / "git"
        git.write_text('#!/bin/sh\nfor arg; do [ "$arg" != ls-tree ] || exit 74; done\n'
                       'exec "' + shutil.which("git") + '" "$@"\n')
        git.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn("could not inspect the remote board", out)
        self.assertEqual(self.head(self.remote), before)
        self.assertEqual(self.run_in(self.here / ".lattice", "git", "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)[0], 1)

    def test_an_incoming_merge_link_cannot_overwrite_another_board(self):
        self.task(self.here, "first")
        self.script("board_update.sh", "--apply", cwd=self.here)
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.run_in(self.here, "lattice", "comment", "DP-1", "said here", "--actor", "human:owner")
        self.run_in(self.there, "lattice", "comment", "DP-1", "said there", "--actor", "human:owner")
        event = next((self.here / ".lattice/events").glob("task_*.jsonl")).name
        victim = pathlib.Path(self.tmp.name, "victim")
        victim.write_text("outside board\n")
        (self.there / ".lattice/events" / (event + ".ours")).symlink_to(victim)
        self.run_in(self.there / ".lattice", "git", "add", "--", "events", "tasks")
        self.run_in(self.there / ".lattice", "git", "commit", "-q", "-m", "add fixture link")
        self.run_in(self.there / ".lattice", "git", "push", "-q", "origin", "main")
        pushed = self.head(self.remote)
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 1, out)
        self.assertIn("the remote board holds a symbolic link", out)
        self.assertEqual(victim.read_text(), "outside board\n")
        self.assertEqual(self.head(self.remote), pushed)
        self.assertEqual(self.run_in(self.here / ".lattice", "git", "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)[0], 1)
        self.assertIn("said here", self.run_in(self.here, "lattice", "comments", "DP-1", "--json")[1])
        self.assertEqual(self.run_in(self.here / ".lattice", "git", "status", "--porcelain")[1], "")

    def test_event_merge_keeps_files_named_like_old_merge_scratch(self):
        self.task(self.here, "first")
        self.script("board_update.sh", "--apply", cwd=self.here)
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.run_in(self.here, "lattice", "comment", "DP-1", "said here", "--actor", "human:owner")
        self.run_in(self.there, "lattice", "comment", "DP-1", "said there", "--actor", "human:owner")
        event = next((self.here / ".lattice/events").glob("task_*.jsonl")).name
        saved = self.there / ".lattice/events" / (event + ".ours")
        saved.write_text("keep this file\n")
        self.run_in(self.there / ".lattice", "git", "add", "--", "events", "tasks")
        self.run_in(self.there / ".lattice", "git", "commit", "-q", "-m", "keep fixture file")
        self.run_in(self.there / ".lattice", "git", "push", "-q", "origin", "main")
        code, out = self.script("board_update.sh", "--apply", cwd=self.here, check=False)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.here / ".lattice/events" / saved.name).read_text(), "keep this file\n")
        comments = self.run_in(self.here, "lattice", "comments", "DP-1", "--json")[1]
        self.assertIn("said here", comments)
        self.assertIn("said there", comments)


if __name__ == "__main__":
    unittest.main()
