"""privacy_check.py through the real pre-commit, commit-msg and pre-push hooks, in throwaway repositories.

Every name and domain here is invented. Each value the check must catch is put
together at run time, so this file passes the check itself.

Run: python3 -m unittest discover -s swe/.claude/scripts -p 'test_*.py'
"""
import base64
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zlib

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = ("pre-commit", "commit-msg", "pre-push", "privacy_check.py", "tells_check.py")


def joined(*parts):
    return "".join(parts)


HOME_PATH = joined("/ho", "me/zedlin/notes.cfg")
EMAIL = joined("ops", "@", "quillmore-dairy", ".net")
TOKEN = joined("gh", "p_", "Q" * 36)


def png(text):
    def chunk(kind, body):
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"tEXt", b"Comment\0" + text.encode()) + chunk(b"IEND", b"")


class PrivacyHooks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.home = self.root / "home"
        work = self.root / "work"
        for folder in ("home", "work/quillmore-dairy", "work/notes"):
            (self.root / folder).mkdir(parents=True)
        self.repo = work / "public-kit"
        self.remote = self.root / "remote.git"
        self.git(self.root, "init", "-q", "--bare", str(self.remote))
        self.git(work, "init", "-q", "-b", "main", "public-kit")
        for key, value in (("user.name", "Quentin Marlowe"), ("user.email", "quentin@example.org")):
            self.git(self.repo, "config", key, value)
        self.git(self.repo, "remote", "add", "origin", str(self.remote))
        self.write(".privacy-allow", "# public values\n")
        self.assertEqual(self.commit("chore: start").returncode, 0)
        for name in HOOKS:
            shutil.copy(HERE / name, self.repo / ".git/hooks" / name)
            (self.repo / ".git/hooks" / name).chmod(0o755)

    def git(self, cwd, *args, check=True):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check,
                              timeout=60, start_new_session=True)

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        self.git(self.repo, "add", path)

    def commit(self, message, hooks=True):
        skip = [] if hooks else ["-c", "core.hooksPath=%s" % (self.root / "no-hooks")]
        return self.git(self.repo, *skip, "commit", "-q", "-m", message, check=False)

    def push(self, remote="origin", hooks=True):
        skip = [] if hooks else ["-c", "core.hooksPath=%s" % (self.root / "no-hooks")]
        return self.git(self.repo, *skip, "push", "-q", remote, "main", check=False)

    def head(self):
        return self.git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def refused(self, done, *expected):
        self.assertNotEqual(done.returncode, 0, done.stderr)
        for text in expected:
            self.assertIn(text, done.stderr)

    def test_a_staged_home_path_cancels_the_commit_and_changes_nothing(self):
        head = self.head()
        self.write("docs/setup.cfg", "copy it from %s\n" % HOME_PATH)
        done = self.commit("docs: add setup notes")
        self.refused(done, "docs/setup.cfg:1: home path: " + joined("/ho", "me/zedlin"), "use ~/",
                     "Git cancelled the commit")
        self.assertEqual(self.head(), head)
        self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only").stdout, "docs/setup.cfg\n")

    def test_each_shape_is_named_by_path_line_and_kind(self):
        self.write("notes.cfg", "\n".join((
            "mail " + EMAIL,
            "build at http://" + joined("build01", ".corp") + ":8080/",
            "server " + joined("10.20", ".30.40"),
            "acted as " + joined("human:", "zedlin"),
            "tenant " + joined("1f0c9d2e-4b7a", "-4c3e-9d21-6a5f3e8b7c10"),
            joined('{"customer', '": "Ottoline Varga"}'),
            "role " + joined("arn:aws:iam::", "481516234200", ":role/deploy"),
        )) + "\n")
        self.refused(self.commit("docs: add notes"), "notes.cfg:1: email", "notes.cfg:2: internal host",
                     "notes.cfg:3: IP address", "notes.cfg:4: actor label", "notes.cfg:5: identifier",
                     "notes.cfg:6: named field", "notes.cfg:7: identifier")

    def test_ordinary_examples_public_links_and_genuine_attribution_pass(self):
        self.write("docs/guide.cfg", "\n".join((
            "Clone it to ~/projects/<project> and run $HOME/bin/tool as /home/<user>/bin/tool.",
            "Write to user@example.com or <email>; see https://github.com/upstream-org/upstream-tool",
            "and https://docs.python.org/3/library/re.html. The test server is 192.0.2.10 or 127.0.0.1.",
            "Record it as human:<name>.",
            "Copyright 2026 Quentin Marlowe",
        )) + "\n")
        trailer = "Co-authored-by: Rosalind Achterberg <%s>" % joined("rosalind", "@", "achterberg-works.net")
        done = self.commit("docs: add the guide\n\n" + trailer)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_commit_message_is_checked(self):
        self.write("a.cfg", "steady\n")
        self.refused(self.commit("fix: reply to " + EMAIL), "commit message:1: email: " + EMAIL)
        self.assertEqual(self.commit("fix: reply to the reporter").returncode, 0)

    def test_names_read_from_this_machine_are_found(self):
        names = self.home / ".config/agent-alignment/privacy-names"
        names.parent.mkdir(parents=True)
        names.write_text("# private\nBrambleton\n")
        self.write("plans.cfg", "Plans for QuillmoreDairy and the Brambleton account; ask quentin.\nKeep notes tidy.\n")
        self.refused(self.commit("docs: add plans"), "plans.cfg:1: name: QuillmoreDairy",
                     "plans.cfg:1: name: Brambleton", "plans.cfg:1: name: quentin")
        names.unlink()
        self.write("plans.cfg", "The Brambleton account.\nKeep notes tidy.\n")
        done = self.commit("docs: add plans")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_folder_name_the_tracked_files_already_hold_is_public_here(self):
        (self.root / "work/toolbox").mkdir()
        self.write("README.cfg", "Built with toolbox.\n")
        self.assertEqual(self.commit("docs: add the readme", hooks=False).returncode, 0)
        self.write("guide.cfg", "Run toolbox, then ask about quillmore-dairy.\n")
        done = self.commit("docs: add the guide")
        self.refused(done, "guide.cfg:1: name: quillmore-dairy")
        self.assertNotIn("name: toolbox", done.stderr)

    def test_a_push_judges_folder_names_by_what_the_remote_already_has(self):
        (self.root / "work/toolbox").mkdir()
        self.write("README.cfg", "Built with toolbox.\n")
        self.assertEqual(self.commit("docs: add the readme", hooks=False).returncode, 0)
        self.assertEqual(self.push(hooks=False).returncode, 0)
        self.write("guide.cfg", "Run toolbox, then ask about quillmore-dairy.\n")
        self.assertEqual(self.commit("docs: add the guide", hooks=False).returncode, 0)
        done = self.push()
        self.refused(done, "guide.cfg:1: name: quillmore-dairy")
        self.assertNotIn("name: toolbox", done.stderr)

    def test_an_allowed_value_passes_and_a_credential_never_does(self):
        self.write("package.json", joined('{"author', '": "Ottoline Varga"}\n'))
        self.refused(self.commit("chore: add the package"), "named field: Ottoline Varga")
        self.write(".privacy-allow", "# public values\nOttoline Varga\n")
        self.assertEqual(self.commit("chore: add the package").returncode, 0)
        self.write("config.py", 'API = "%s"\n' % TOKEN)
        done = self.commit("feat: add the config")
        self.refused(done, "config.py:1: credential: value not shown", "rotate it")
        self.write(".privacy-allow", "# public values\n%s\n" % TOKEN)
        done = self.commit("feat: add the config")
        self.refused(done, "line 2 of .privacy-allow has a credential shape")
        self.assertNotIn(TOKEN, done.stderr)

    def test_a_password_inside_a_url_stays_a_hidden_credential(self):
        secret = joined("Sup3r", "S3cretValue9")
        host = joined("db", ".internal")
        self.write("db.cfg", "DATABASE_URL = postgres://app:%s@%s:5432/app\n" % (secret, host))
        done = self.commit("feat: add the database")
        self.refused(done, "db.cfg:1: credential: value not shown")
        self.assertNotIn(secret, done.stderr)
        self.write(".privacy-allow", "# public values\n%s@%s\n" % (secret, host))
        done = self.commit("feat: add the database")
        self.refused(done, "db.cfg:1: credential: value not shown")
        self.assertNotIn(secret, done.stderr)
        self.write(".privacy-allow", "# public values\n")
        self.write("db.cfg", joined("DATABASE_URL = postgres://app:", "p%40", secret, "@", host, ":5432/app\n"))
        done = self.commit("feat: add the database")
        self.refused(done, "db.cfg:1: credential: value not shown")
        self.assertNotIn(secret, done.stderr)

    def test_only_a_trailer_or_copyright_line_gets_the_attribution_pass(self):
        self.write("count.py", "n = len(c)  # mail %s\n" % EMAIL)
        self.refused(self.commit("feat: count"), "count.py:1: email")
        self.write("count.py", "created-by: %s\n" % EMAIL)
        self.refused(self.commit("feat: count"), "count.py:1: email")
        self.write("count.py", "n = len(c)\n")
        self.assertEqual(self.commit("fix: count\n\n#42 reply to " + EMAIL).returncode, 0)
        self.refused(self.push(), "commit message:3: email")

    def test_comment_lines_git_strips_from_an_edited_message_are_not_checked(self):
        self.write("quillmore-dairy.cfg", "steady\n")
        self.assertEqual(self.commit("docs: add notes", hooks=False).returncode, 0)
        self.write("quillmore-dairy.cfg", "steady still\n")
        done = self.git(self.repo, "-c", "core.editor=true", "commit", "-q", "-e", "-m", "docs: tidy notes", check=False)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_words_of_the_git_name_match_only_as_written(self):
        self.git(self.repo, "config", "user.name", "Mark Marlowe")
        self.write("todo.cfg", "mark the task done\n")
        done = self.commit("docs: add the list")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.write("todo.cfg", "ask Mark about it\n")
        self.refused(self.commit("docs: ask about it"), "todo.cfg:1: name: Mark")

    def test_every_binary_waits_for_its_blob_id_and_image_metadata_is_read(self):
        self.write("tool.bin", b"\x00\x01made up\x00")
        blob = self.git(self.repo, "rev-parse", ":tool.bin").stdout.strip()
        self.refused(self.commit("feat: add the tool"), "tool.bin: binary: " + blob)
        self.write("shot.png", png("Author " + HOME_PATH))
        self.refused(self.commit("feat: add the tool"), "shot.png: metadata: home path")
        self.write("shot.png", png("Software paint"))
        image = self.git(self.repo, "rev-parse", ":shot.png").stdout.strip()
        self.refused(self.commit("feat: add the tool"), "shot.png: binary: " + image)
        self.write(".privacy-allow", "# public values\n%s\n%s\n" % (blob, image))
        done = self.commit("feat: add the tool")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_only_added_lines_count_even_in_a_path_with_a_space(self):
        old = "old server %s\n" % joined("10.20", ".30.40")
        self.write("my notes.cfg", old + "steady\n")
        self.assertEqual(self.commit("docs: add notes", hooks=False).returncode, 0)
        self.write("my notes.cfg", old)
        done = self.commit("docs: drop a line")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.write("my notes.cfg", old + "a new line\n")
        done = self.commit("docs: add a line")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_encoded_text_and_renamed_paths_are_checked(self):
        self.write("data.cfg", "data: %s\n" % base64.b64encode(HOME_PATH.encode()).decode())
        self.refused(self.commit("chore: add data"), "data.cfg:1: home path (base64)")
        self.write("data.cfg", "steady\n")
        self.assertEqual(self.commit("chore: add data").returncode, 0)
        self.git(self.repo, "mv", "data.cfg", "quillmore-dairy.cfg")
        self.refused(self.commit("chore: rename data"), "quillmore-dairy.cfg: file name: name: quillmore-dairy")

    def test_only_no_verify_removes_the_allow_file_and_then_nothing_is_checked(self):
        self.git(self.repo, "rm", "-q", ".privacy-allow")
        self.refused(self.commit("chore: stop checking"), "this removes .privacy-allow", "commit refused")
        self.assertEqual(self.commit("chore: stop checking", hooks=False).returncode, 0)
        self.refused(self.push(), "this removes .privacy-allow", "push refused")
        self.assertEqual(self.git(self.remote, "for-each-ref").stdout, "")
        self.write("notes.cfg", HOME_PATH + "\n")
        self.assertEqual(self.commit("chore: add notes").returncode, 0)

    def test_a_file_name_or_binary_that_only_a_merge_brings_in_is_checked(self):
        old = ["old line %d" % n for n in range(9)]
        old[0] = "copy it from " + HOME_PATH
        self.write("shared.cfg", "\n".join(old) + "\n")
        self.assertEqual(self.commit("docs: add shared", hooks=False).returncode, 0)
        self.assertEqual(self.push(hooks=False).returncode, 0)
        self.git(self.repo, "checkout", "-q", "-b", "side")
        self.write("shared.cfg", "\n".join(old[:6] + ["side edit"] + old[7:]) + "\n")
        self.assertEqual(self.commit("docs: edit on the side").returncode, 0)
        self.git(self.repo, "checkout", "-q", "main")
        self.write("shared.cfg", "\n".join(old[:3] + ["main edit"] + old[4:]) + "\n")
        self.assertEqual(self.commit("docs: edit on main").returncode, 0)
        self.git(self.repo, "merge", "-q", "--no-commit", "side")
        self.write("quillmore-dairy.cfg", "steady\n")
        self.write("tool.bin", b"\x00\x01made up\x00")
        blob = self.git(self.repo, "rev-parse", ":tool.bin").stdout.strip()
        self.assertEqual(self.commit("merge side", hooks=False).returncode, 0)
        done = self.push()
        self.refused(done, "quillmore-dairy.cfg: file name: name: quillmore-dairy", "tool.bin: binary: " + blob)
        self.assertNotIn("home path", done.stderr)

    def test_a_removal_by_a_merge_or_a_rewind_is_refused_at_push(self):
        self.assertEqual(self.push(hooks=False).returncode, 0)
        start = self.head()
        self.git(self.repo, "checkout", "-q", "--orphan", "side")
        self.git(self.repo, "rm", "-q", "-r", "--cached", ".")
        (self.repo / ".privacy-allow").unlink()
        self.write("other.txt", "steady\n")
        self.assertEqual(self.commit("chore: start the side").returncode, 0)
        self.git(self.repo, "merge", "-q", "--no-commit", "--allow-unrelated-histories", "-s", "ours", "main")
        self.assertEqual(self.commit("merge main", hooks=False).returncode, 0)
        for refspec in ("side", "side:main"):
            done = self.git(self.repo, "push", "-q", "origin", refspec, check=False)
            self.refused(done, "this removes .privacy-allow", "push refused")
        done = self.git(self.repo, "push", "-q", "--force", "origin", "side~1:main", check=False)
        self.refused(done, "this removes .privacy-allow", "push refused")
        self.assertEqual(self.git(self.remote, "for-each-ref", "--format=%(refname) %(objectname)").stdout,
                         "refs/heads/main %s\n" % start)

    def test_a_credential_in_a_file_name_is_never_printed(self):
        encoded = joined("gh", "p%5F", "Q" * 36)
        hidden = base64.urlsafe_b64encode(TOKEN.encode()).decode()
        for path in ("keys/%s.txt" % TOKEN, "keys/%s.txt" % encoded, "%s.txt" % hidden):
            self.write(path, "steady\n")
        done = self.commit("chore: add keys")
        self.refused(done, "<a path holding a credential>: file name: credential: value not shown")
        for secret in (TOKEN, encoded, hidden, "Q" * 36):
            self.assertNotIn(secret, done.stderr)
        self.assertEqual(self.commit("chore: add keys", hooks=False).returncode, 0)
        done = self.push()
        self.refused(done, "credential")
        for secret in (TOKEN, encoded, hidden, "Q" * 36):
            self.assertNotIn(secret, done.stderr)

    def test_a_push_checks_each_commit_even_after_a_later_one_removed_the_text(self):
        self.write("setup.cfg", "copy it from %s\n" % HOME_PATH)
        self.assertEqual(self.commit("docs: add setup", hooks=False).returncode, 0)
        leak = self.head()
        self.write("setup.cfg", "copy it from ~/notes.cfg\n")
        self.assertEqual(self.commit("docs: tidy setup").returncode, 0)
        self.refused(self.push(), "%s setup.cfg:1: home path" % leak[:12], "Git cancelled the push")
        self.assertEqual(self.git(self.remote, "for-each-ref").stdout, "")

    def test_a_commit_already_on_another_remote_is_checked_on_the_way_to_this_one(self):
        private = self.root / "private.git"
        self.git(self.root, "init", "-q", "--bare", str(private))
        self.git(self.repo, "remote", "add", "private", str(private))
        self.write("setup.cfg", "copy it from %s\n" % HOME_PATH)
        self.assertEqual(self.commit("docs: add setup", hooks=False).returncode, 0)
        self.assertEqual(self.push("private", hooks=False).returncode, 0)
        self.refused(self.push(), "setup.cfg:1: home path", "Git cancelled the push")

    def test_a_clean_push_passes(self):
        self.write("tool.py", "print('steady')\n")
        self.assertEqual(self.commit("feat: add the tool").returncode, 0)
        done = self.push()
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
