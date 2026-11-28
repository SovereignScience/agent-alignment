"""kit_pull.sh against a throwaway kit, a project that holds a clone of it and two throwaway SSH keys."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("kit_pull.sh")
GUIDE = SCRIPT.parent.parent / "LATTICE_ONBOARDING.md"
BASH = shutil.which("bash")
KIT_ADDRESS = "https://github.com/SovereignScience/agent-alignment"
# Stands in for GnuPG, or for gpgsm when it has that name: signs anything and calls every signature good.
FAKE_GPG = """#!/bin/sh
case "$0" in *gpgsm) kind="SIGNED MESSAGE" ;; *) kind="PGP SIGNATURE" ;; esac
case " $* " in
*" --verify "*) printf '[GNUPG:] NEWSIG\\n[GNUPG:] GOODSIG 0123456789ABCDEF anyone\\n' ;;
*) cat >/dev/null
   printf -- '-----BEGIN %s-----\\n\\nAAAA\\n-----END %s-----\\n' "$kind" "$kind"
   printf '[GNUPG:] BEGIN_SIGNING\\n[GNUPG:] SIG_CREATED D\\n' >&2 ;;
esac
"""


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is not installed")
class KitPull(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env["HOME"] = str(self.home)
        self.owner, self.stranger = self.root / "owner", self.root / "stranger"
        for key in (self.owner, self.stranger):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", key.name, "-f", str(key)],
                           env=self.env, check=True, capture_output=True)
        self.signers = self.home / ".config/agent-alignment/allowed_signers"
        self.signers.parent.mkdir(parents=True)
        self.signers.write_text('owner@example.com namespaces="git" %s' % self.owner.with_suffix(".pub").read_text())

        self.kit = self.root / "kit"
        (self.kit / "swe/scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.kit / "swe/scripts/kit_pull.sh")
        (self.kit / ".gitignore").write_text("__pycache__/\n")
        self.git(self.kit, "init", "-q", "-b", "main")
        self.git(self.kit, "add", ".gitignore")
        self.release("v1.0.0")

        self.project = self.root / "project"
        self.project.mkdir()
        self.git(self.project, "init", "-q", "-b", "main")
        (self.project / "README.md").write_text("a project\n")
        self.git(self.project, "add", "README.md")
        self.git(self.project, "commit", "-q", "-m", "add readme")
        (self.project / ".git/info/exclude").write_text("/.agent-alignment/\n")
        self.clone = self.project / ".agent-alignment"
        self.git(self.project, "clone", "-q", "--no-checkout", str(self.kit), str(self.clone))
        self.git(self.clone, "checkout", "-q", "--detach", "refs/tags/v1.0.0")

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True,
                              text=True).stdout.strip()

    def release(self, tag, *how):
        """A new commit in the kit that changes the pull script, tagged; signed by the owner unless told how."""
        with open(self.kit / "swe/scripts/kit_pull.sh", "a") as script:
            script.write("# %s\n" % tag)
        self.git(self.kit, "add", "swe")
        self.git(self.kit, "commit", "-q", "-m", "release " + tag)
        how = how or ("-c", "gpg.format=ssh", "-c", "user.signingkey=%s" % self.owner, "tag", "-s", "-m", tag)
        self.git(self.kit, *how, tag)
        return self.git(self.kit, "rev-parse", "HEAD")

    def by_the_stranger(self, tag):
        return ("-c", "gpg.format=ssh", "-c", "user.signingkey=%s" % self.stranger, "tag", "-s", "-m", tag)

    def files(self, root, skip):
        return {str(path): path.read_bytes() for path in sorted(root.rglob("*"))
                if path.is_file() and not path.is_symlink() and skip not in path.parents}

    def head(self, where=None):
        return self.git(where or self.clone, "rev-parse", "HEAD")

    def state(self):
        """What a pull may change in the clone: its commit, its tags and branches, and its files."""
        return self.head(), self.git(self.clone, "for-each-ref"), self.files(self.clone, self.clone / ".git")

    def pull(self, *args, script=None, **extra):
        """Run the clone's own copy from the top of the project; nothing outside the clone may change."""
        status = self.git(self.project, "status", "--porcelain", "--ignored")
        outside = self.files(self.root, self.clone)
        run = subprocess.run([BASH, str(script or ".agent-alignment/swe/scripts/kit_pull.sh"), *args],
                             cwd=self.project, env=dict(self.env, **extra), capture_output=True, text=True, timeout=60)
        self.assertEqual(self.files(self.root, self.clone), outside)
        self.assertEqual(self.git(self.project, "status", "--porcelain", "--ignored"), status)
        return run.returncode, run.stdout + run.stderr

    def refused(self, tag, reason):
        """The pull stops with this reason and the clone keeps the commit, the tags and the files it had."""
        before = self.state()
        code, out = self.pull(tag)
        self.assertEqual(code, 1, out)
        self.assertIn("STOP: ", out)
        self.assertIn(reason, out)
        self.assertEqual(self.state(), before)

    def guide_block(self, holds, cwd, **filled):
        """Run a block of the guide as it is printed, pasted whole, with its placeholders filled in."""
        block = next(part for part in GUIDE.read_text().split("```") if holds in part)
        for placeholder, value in filled.items():
            block = block.replace(placeholder, str(value))
        run = subprocess.run([BASH, "-c", block], cwd=cwd, env=self.env, capture_output=True, text=True, timeout=60)
        return run.returncode, run.stdout + run.stderr

    def first_run(self, tag, kit=None):
        shutil.rmtree(self.clone)
        return self.guide_block("clone -q --no-checkout", self.project, **{"<tag>": tag, "<kit>": kit or self.kit})

    def fake_gpg(self, setting, name):
        program = self.root / name
        program.write_text(FAKE_GPG)
        program.chmod(0o755)
        self.git(self.home, "config", "--global", setting, str(program))

    def test_a_release_signed_by_a_listed_key_moves_the_clone_to_it(self):
        commit = self.release("v1.1.0")
        code, out = self.pull("v1.1.0")
        self.assertEqual(code, 0, out)
        self.assertIn("is now at release v1.1.0", out)
        self.assertEqual(self.head(), commit)
        self.assertEqual(self.git(self.clone, "status", "--porcelain"), "")

    def test_it_reports_where_the_clone_is_where_it_goes_and_what_differs(self):
        self.release("v1.1.0")
        code, out = self.pull("v1.1.0")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("now      v1.0.0 ("), out)
        self.assertTrue(lines[1].startswith("release  v1.1.0 ("), out)
        self.assertIn("signed by a key in", lines[1])
        self.assertIn(" swe/scripts/kit_pull.sh | 1 +", lines)
        self.assertIn(" 1 file changed, 1 insertion(+)", lines)
        self.assertTrue(lines[-1].startswith("DONE: "), out)
        # The next run names the release the clone was moved to, and says when it is on none.
        self.assertTrue(self.pull("--report", "v1.1.0")[1].startswith("now      v1.1.0 ("))
        self.git(self.clone, "tag", "-d", "v1.1.0")
        self.assertTrue(self.pull("--report", "v1.0.0")[1].startswith("now      not on a release ("))

    def test_report_only_checks_and_reports_and_moves_nothing(self):
        self.release("v1.1.0")
        before = self.state()
        code, out = self.pull("--report", "v1.1.0")
        self.assertEqual(code, 0, out)
        self.assertIn("release  v1.1.0 (", out)
        self.assertIn(" 1 file changed, 1 insertion(+)", out)
        self.assertIn("DONE: report only", out)
        self.assertEqual(self.state(), before)
        self.release("v1.2.0", "tag", "-a", "-m", "v1.2.0")
        code, out = self.pull("--report", "v1.2.0")
        self.assertEqual(code, 1, out)
        self.assertIn("has no signature from a key in", out)
        self.assertEqual(self.pull("--report")[0], 64)
        # On the release already, but without its tag: a report still writes nothing.
        self.git(self.clone, "tag", "-d", "v1.0.0")
        before = self.state()
        code, out = self.pull("--report", "v1.0.0")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.state(), before)

    def test_a_second_run_with_the_same_name_changes_nothing_and_says_so(self):
        self.release("v1.1.0")
        for name in ("v1.1.0", "latest"):
            with self.subTest(name=name):
                self.assertEqual(self.pull(name)[0], 0)
                after = self.state()
                code, out = self.pull(name)
                self.assertEqual(code, 0, out)
                self.assertIn("was already at release v1.1.0; nothing changed", out)
                self.assertEqual(self.state(), after)

    def test_latest_takes_the_newest_release_number_by_number(self):
        self.release("v1.2.0")
        newest = self.release("v1.10.0")
        self.release("v1.9.5")
        # Signed, and named higher, but not release names: one or two numbers, a leading zero, a suffix.
        for name in ("v3", "v3.0", "v03.0.0", "v3.0.0-rc1"):
            self.release(name)
        self.git(self.kit, "tag", "version-9")
        code, out = self.pull("latest")
        self.assertEqual(code, 0, out)
        self.assertIn("latest   v1.10.0, the newest release", out)
        self.assertIn("is now at release v1.10.0", out)
        self.assertEqual(self.head(), newest)

    def test_latest_only_goes_forward_and_naming_the_release_still_goes_back(self):
        self.release("v1.1.0")
        self.assertEqual(self.pull("v1.1.0")[0], 0)
        # A kit that lists less than the clone has.
        self.git(self.kit, "tag", "-d", "v1.1.0")
        self.refused("latest", "v1.0.0, is not ahead of this clone")
        # A kit whose newest release is on another line of history: refused, and no tag is left behind.
        self.git(self.kit, "switch", "-q", "-c", "another-line", "v1.0.0")
        elsewhere = self.release("v1.2.0")
        self.refused("latest", "v1.2.0, is not ahead of this clone")
        for name, commit in (("v1.2.0", elsewhere), ("v1.0.0", self.git(self.kit, "rev-parse", "v1.0.0^{commit}"))):
            with self.subTest(named=name):
                code, out = self.pull(name)
                self.assertEqual(code, 0, out)
                self.assertIn("is now at release " + name, out)
                self.assertEqual(self.head(), commit)

    def test_latest_stops_when_the_newest_release_does_not_verify(self):
        self.release("v1.1.0")
        self.release("v1.2.0", *self.by_the_stranger("v1.2.0"))
        self.refused("latest", "release v1.2.0 has no signature from a key in")

    def test_an_unsigned_tag_is_refused(self):
        self.release("v1.1.0", "tag", "-a", "-m", "v1.1.0")
        self.release("v1.2.0", "tag")
        for tag in ("v1.1.0", "v1.2.0"):
            with self.subTest(tag=tag):
                self.refused(tag, "has no signature from a key in")

    def test_a_tag_signed_by_a_key_that_is_not_allowed_is_refused(self):
        self.release("v1.1.0", *self.by_the_stranger("v1.1.0"))
        self.refused("v1.1.0", "has no signature from a key in")

    def test_a_file_that_lists_two_keys_takes_a_release_signed_by_either(self):
        with open(self.signers, "a") as file:
            file.write('other@example.com namespaces="git" %s' % self.stranger.with_suffix(".pub").read_text())
        self.release("v1.1.0", *self.by_the_stranger("v1.1.0"))
        self.release("v1.2.0")
        for tag in ("v1.1.0", "v1.2.0"):
            with self.subTest(tag=tag):
                code, out = self.pull(tag)
                self.assertEqual(code, 0, out)
                self.assertIn("is now at release " + tag, out)

    def test_a_signature_that_is_not_an_ssh_one_is_refused_even_where_git_would_accept_it(self):
        kinds = (("v1.1.0", "openpgp", "gpg.program", "gpg"), ("v1.2.0", "x509", "gpg.x509.program", "gpgsm"))
        for tag, kind, setting, name in kinds:
            with self.subTest(kind=kind):
                self.fake_gpg(setting, name)
                self.release(tag, "-c", "gpg.format=" + kind, "tag", "-s", "-m", tag)
                self.git(self.kit, "verify-tag", tag)
                self.refused(tag, "has no signature from a key in")
        for tag, kind, _, _ in kinds:
            with self.subTest(first_run=kind):
                code, out = self.first_run(tag)
                self.assertNotEqual(code, 0, out)
                self.assertEqual([path.name for path in self.clone.iterdir()], [".git"])

    def test_an_older_signed_release_served_under_a_newer_name_is_refused(self):
        self.release("v1.1.0")
        self.assertEqual(self.pull("v1.1.0")[0], 0)
        self.git(self.kit, "update-ref", "refs/tags/v1.2.0", self.git(self.kit, "rev-parse", "refs/tags/v1.0.0"))
        self.refused("v1.2.0", "was signed under the name v1.0.0")
        self.refused("latest", "was signed under the name v1.0.0")

    def test_a_tag_the_kit_does_not_have_is_refused(self):
        self.refused("v9.0.0", "release v9.0.0 could not be fetched")

    def test_a_name_that_is_not_a_release_is_refused(self):
        self.release("v1.1.0")
        for name in ("v1", "v1.1"):
            self.release(name)
        for name in ("main", "v1.1.0;id", "--upload-pack=id", "refs/tags/v1.1.0", "v1.١.0", "v1", "v1.1",
                     "v1.1.0.0", "v01.1.0", "v1.1.0-rc1", "v1.1.9999999999", ""):
            with self.subTest(name=name):
                self.refused(name, "a release is named like v1.2.0")
        self.assertEqual(self.pull()[0], 64)

    def test_a_clone_with_local_changes_is_refused_and_its_files_are_listed(self):
        self.release("v1.1.0")
        with open(self.clone / "swe/scripts/kit_pull.sh", "a") as script:
            script.write("# edited in the project\n")
        (self.clone / "left-by-a-session").write_text("not the kit's\n")
        self.refused("v1.1.0", "has local changes")
        out = self.pull("--report", "v1.1.0")[1]
        self.assertIn(" M swe/scripts/kit_pull.sh\n?? left-by-a-session\n", out)
        self.assertIn("the first 20 of 2:", out)
        self.assertFalse((self.clone / ".git/FETCH_HEAD").exists())

    def test_ignored_files_are_named_and_do_not_stop_a_pull(self):
        commit = self.release("v1.1.0")
        (self.clone / "swe/scripts/__pycache__").mkdir()
        (self.clone / "swe/scripts/__pycache__/kit.pyc").write_text("made by running a kit script\n")
        code, out = self.pull("v1.1.0")
        self.assertEqual(code, 0, out)
        self.assertIn("note     ignored files present, not part of a release", out)
        self.assertIn("!! swe/scripts/__pycache__/\n", out)
        self.assertEqual(self.head(), commit)

    def test_a_clone_git_cannot_report_on_is_refused(self):
        self.release("v1.1.0")
        (self.clone / ".git/index").write_bytes(b"not an index")
        self.refused("v1.1.0", "git status failed")
        self.assertFalse((self.clone / ".git/FETCH_HEAD").exists())

    def test_the_guides_first_run_takes_the_signed_tag_when_a_branch_has_its_name(self):
        commit = self.release("v1.1.0")
        # The kit's default branch is named like the release, so a new clone has that branch too.
        self.git(self.kit, "switch", "-q", "-c", "v1.1.0")
        (self.kit / "swe/scripts/kit_pull.sh").write_text('touch "$HOME/ran-from-the-branch"\necho "DONE: a fake"\n')
        self.git(self.kit, "commit", "-q", "-am", "a branch named like the release")
        code, out = self.first_run("v1.1.0")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / "ran-from-the-branch").exists(), out)
        self.assertEqual(self.head(), commit)
        self.assertIn('Good "git" signature for owner@example.com', out)
        self.assertIn("was already at release v1.1.0", out)
        self.assertEqual(self.git(self.clone, "remote", "get-url", "--push", "origin"), "no-push")
        shared = [path for path in (self.clone / ".git/objects").rglob("*") if path.is_file() and path.stat().st_nlink > 1]
        self.assertEqual(shared, [], "the clone shares object files with the kit in a local folder")

    def test_the_guides_first_run_checks_nothing_out_when_the_signature_fails(self):
        self.release("v1.1.0", *self.by_the_stranger("v1.1.0"))
        code, out = self.first_run("v1.1.0")
        self.assertNotEqual(code, 0, out)
        self.assertEqual([path.name for path in self.clone.iterdir()], [".git"])
        self.assertNotIn("DONE", out)

    def test_the_guides_first_run_checks_nothing_out_when_an_older_release_is_served_under_the_name(self):
        self.release("v1.1.0")
        self.git(self.kit, "update-ref", "refs/tags/v1.2.0", self.git(self.kit, "rev-parse", "refs/tags/v1.0.0"))
        code, out = self.first_run("v1.2.0")
        self.assertNotEqual(code, 0, out)
        self.assertEqual([path.name for path in self.clone.iterdir()], [".git"])
        self.assertNotIn("DONE", out)

    def test_the_guides_release_blocks_sign_check_and_publish_a_tag_a_project_can_pull(self):
        published = self.root / "published.git"
        self.git(self.kit, "clone", "-q", "--bare", str(self.kit), str(published))
        self.git(self.kit, "remote", "add", "origin", str(published))
        self.git(self.clone, "remote", "set-url", "origin", str(published))
        code, out = self.guide_block("config gpg.format ssh", self.kit,
                                     **{"<path to your public SSH key>": self.owner.with_suffix(".pub")})
        self.assertEqual(code, 0, out)
        self.assertIn("SHA256:", out)
        self.assertEqual(self.git(self.home, "config", "--global", "--default", "unset", "--get", "gpg.format"), "unset")
        self.release("v1.1.0", "tag")
        self.git(self.kit, "tag", "-d", "v1.1.0")
        self.git(self.kit, "branch", "v1.1.0")
        code, out = self.guide_block("git tag -s", self.kit, **{"<tag>": "v1.1.0"})
        self.assertEqual(code, 0, out)
        self.assertIn('Good "git" signature for owner@example.com', out)
        code, out = self.guide_block("git push origin", self.kit, **{"<tag>": "v1.1.0"})
        self.assertEqual(code, 0, out)
        code, out = self.pull("latest")
        self.assertEqual(code, 0, out)
        self.assertIn("is now at release v1.1.0", out)

    def test_the_guides_release_block_stops_on_a_tag_that_is_not_ssh_signed(self):
        self.fake_gpg("gpg.program", "gpg")
        self.git(self.kit, "config", "gpg.format", "openpgp")
        code, out = self.guide_block("git tag -s", self.kit, **{"<tag>": "v1.1.0"})
        self.assertNotEqual(code, 0, out)
        self.git(self.kit, "verify-tag", "v1.1.0")

    def test_the_guides_own_kit_takes_only_what_its_developer_signed(self):
        self.release("v1.1.0")
        own = self.root / "own-kit"
        self.signers.unlink()
        code, out = self.guide_block("remote.origin.tagOpt", self.root, **{KIT_ADDRESS: self.kit, "<your kit>": own})
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git(own, "tag", "--list"), "")
        code, out = self.guide_block("config gpg.format ssh", own,
                                     **{"<path to your public SSH key>": self.stranger.with_suffix(".pub")})
        self.assertEqual(code, 0, out)
        (own / "RULES.md").write_text("a rule of my own\n")
        self.git(own, "add", "RULES.md")
        self.git(own, "commit", "-q", "-m", "add my rule")
        code, out = self.guide_block("git tag -s", own, **{"<tag>": "v1.0.0"})
        self.assertEqual(code, 0, out)
        code, out = self.first_run("v1.0.0", kit=own)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.clone / "RULES.md").read_text(), "a rule of my own\n")
        # A later fetch from the kit it was copied from brings no release of that kit's into it.
        self.git(own, "fetch", "-q", "origin")
        self.assertEqual(self.git(own, "tag", "--list"), "v1.0.0")
        code, out = self.pull("latest")
        self.assertEqual(code, 0, out)
        self.assertIn("was already at release v1.0.0", out)
        # The kit it was copied from is no longer trusted: its releases do not pass.
        self.git(self.clone, "remote", "set-url", "origin", str(self.kit))
        self.refused("v1.1.0", "has no signature from a key in")

    def test_already_at_the_release_changes_nothing_and_says_so(self):
        before = self.state()
        code, out = self.pull("v1.0.0")
        self.assertEqual(code, 0, out)
        self.assertIn("was already at release v1.0.0", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.state(), before)

    def test_without_the_allowed_signers_file_nothing_is_fetched(self):
        self.release("v1.1.0")
        self.signers.unlink()
        self.refused("v1.1.0", "no allowed signers file")
        self.assertFalse((self.clone / ".git/FETCH_HEAD").exists())

    def test_git_variables_from_the_terminal_do_not_send_it_to_the_project(self):
        commit = self.release("v1.1.0")
        code, out = self.pull("v1.1.0", GIT_DIR=str(self.project / ".git"), GIT_WORK_TREE=str(self.project))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.head(), commit)

    def test_a_folder_that_is_not_the_projects_own_clone_is_left_alone(self):
        self.release("v1.1.0")
        elsewhere = self.root / "elsewhere"
        self.clone.rename(elsewhere)
        self.clone.mkdir()
        code, out = self.pull("v1.1.0", script=SCRIPT)
        self.assertEqual(code, 1, out)
        self.assertIn("is not a Git clone of its own", out)
        self.clone.rmdir()
        self.clone.symlink_to(elsewhere)
        code, out = self.pull("v1.1.0", script=SCRIPT)
        self.assertEqual(code, 1, out)
        self.assertIn("no .agent-alignment folder", out)
        self.assertNotEqual(self.head(elsewhere), self.git(self.kit, "rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
