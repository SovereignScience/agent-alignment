"""Command decisions under the managed invocation; no input command is executed.

Gcloud syntax: https://cloud.google.com/sdk/gcloud/reference
Project property read: https://cloud.google.com/sdk/gcloud/reference/config/get-value
GitHub API methods and fields: https://cli.github.com/manual/gh_api
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

GUARD = pathlib.Path(__file__).with_name("guard_outward.py")


def decision(guard, command):
    result = subprocess.run(["/usr/bin/python3", "-I", str(guard)], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}), text=True,
        capture_output=True, check=True, timeout=10)
    if not result.stdout.strip():
        return "allow"
    output = json.loads(result.stdout)["hookSpecificOutput"]
    value = output["permissionDecision"]
    if output["hookEventName"] != "PreToolUse" or value not in ("allow", "deny"):
        raise ValueError("invalid hook decision")
    return value


def check_case(guard, expected):
    actual = decision(guard, "git status")
    if actual != expected:
        raise AssertionError("expected %s, got %s" % (expected, actual))


class ShellCases(unittest.TestCase):
    def test_hidden_pushes_are_refused(self):
        commands = [
            'env -S "git push"', 'env --split-string="git push"',
            'env -iS "git push"', 'env -Sgit\\ push',
            'echo "$(git push)"', 'printf "%s" "$(git -C project push)"',
            'echo "$(printf "%s" "$(git push)")"',
            'echo "`git push`"', 'echo $(git push)',
            "sudo -u root git push", "bash -lc 'git push'",
            "find . -exec git push \\;",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_local_work_and_inert_literals_pass(self):
        commands = [
            'git add -u docs/a.md', 'git add --update -- docs/a.md',
            'git config --get core.hooksPath', 'git config --get user.name',
            "echo '$(git push)'", 'echo "\\$(git push)"',
            'echo "$(git status)"', 'echo "$(printf "%s" "$(git status)")"',
            "env -u EXAMPLE git status", 'git status # $(git push)',
            "git commit -m 'fix: parse empty headers'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")

    def test_unreadable_substitutions_are_refused(self):
        for command in ['echo "$(git push"', 'echo "$(git status"']:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")


class HookAndAliasCases(unittest.TestCase):
    def test_commits_that_skip_hooks_are_refused(self):
        commands = [
            "git commit -n -m 'fix: x'", "git commit -nm 'fix: x'",
            "git commit -anm 'fix: x'", "git -C project commit -n -m 'fix: x'",
            "git commit --amend -n", "git -c core.hooksPath=/dev/null commit -m 'fix: x'",
            "git -c core.hookspath= commit -m 'fix: x'",
            "git config core.hooksPath /tmp/none", "git config set core.hooksPath /tmp/none",
            "git config --global core.hooksPath /tmp/none",
            "git config unset core.hooksPath", "git config --unset core.hooksPath",
            "git commit --no-verif -m 'fix: x'", "git commit --no-veri -m 'fix: x'",
            "git --attr-source HEAD commit -n -m 'fix: x'",
            "git -c include.path=/tmp/other.cfg commit -m 'fix: x'",
            "git config include.path /tmp/other.cfg",
            "git -c includeIf.gitdir:/.path=/tmp/other.cfg commit -m 'fix: x'",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null "
            "git commit -m 'fix: x'",
            "env GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/dev/null'\" git commit -m 'fix: x'",
            "export GIT_CONFIG_GLOBAL=/tmp/other.cfg; git commit -m 'fix: x'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_aliases_cannot_hide_a_subcommand(self):
        commands = [
            "git -c alias.p=push p", "git -c alias.p='!git push' p origin",
            "git --config-env=alias.p=HIDDEN p", "git config alias.p push",
            "git config --add alias.p push", "git config set alias.p push",
            "git config --file .git/config alias.p push",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_ordinary_commits_and_config_reads_pass(self):
        commands = [
            "git commit -m 'fix: handle -n in the parser'", "git commit -m -n",
            "git commit -sm 'fix: x'", "git commit -F notes.txt",
            "git commit --author 'N <n@example.com>' -m 'fix: x'",
            "git commit --amend --no-edit", "git commit -v -m 'fix: x'",
            "git commit -m 'fix: x' -- -n", "git switch -c feature/x",
            "git -c core.quotepath=off status", "git config --get alias.p",
            "git config get alias.p", "git config core.hooksPath",
            "git config user.name", "git merge -n feature/x",
            "git merge --no-verify-signatures feature/x", "git commit -m 'fix: x' > commit.log",
            "GIT_PAGER=cat git log -n 3",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")


class RootCases(unittest.TestCase):
    def test_a_session_never_runs_a_command_as_root(self):
        for command in ("sudo ls /etc/claude-code", "sudo -n true", "env X=1 sudo install -m 644 a /etc/a",
                        "doas rm /etc/claude-code/managed-settings.json", "su -c 'id'", "pkexec id",
                        "bash -c 'sudo id'", "true && sudo id"):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")
        for command in ("grep -n sudo swe/scripts/install_isolation.sh", "command -v sudo",
                        "echo 'the owner runs sudo'"):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")


class WrappedCommandCases(unittest.TestCase):
    def test_a_push_or_root_command_behind_a_wrapper_is_still_refused(self):
        commands = [
            "bash -c -- 'git push origin main'", "cat <(git push origin main)",
            "echo 'git push origin main' | bash", "printf 'sudo id' | sh -s",
            "watch -n 1 git push origin main", "setsid git push origin main",
            "exec -a x git push origin main", "env --chdir /tmp git push origin main",
            "git send-pack origin main", "sudoedit /etc/hosts", "busybox su", "$'sudo' ls",
            "setsid sudo ls", "watch -n 1 sudo ls", "bash -c -- 'sudo ls'", "cat <(sudo ls)",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_a_session_cannot_call_itself_a_cloud_session(self):
        for command in ("CLAUDE_CODE_REMOTE=true bash .claude/scripts/cloud_push.sh",
                        "export CLAUDE_CODE_REMOTE=true", "env CLAUDE_CODE_REMOTE=true bash x.sh"):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_ordinary_uses_of_the_same_words_pass(self):
        for command in ("./su --help", "bin/su", "bash scripts/check_drift.sh", "bash -n scripts/x.sh",
                        "bash --version", "diff <(sort a.txt) <(sort b.txt)", "watch -n 1 date",
                        "busybox ls", "cat notes.txt | grep sudo", "echo \"$CLAUDE_CODE_REMOTE\""):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")


class SplitCommandCases(unittest.TestCase):
    def test_a_continued_line_is_read_as_one_command(self):
        commands = [
            "git commit -m 'fix: x' \\\n  --no-verify", "git commit \\\n -n -m 'fix: x'",
            "git \\\n push origin main", "git worktree \\\n prune",
            "lattice status AA-1 \\\n done --actor agent:claude",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_a_redirect_does_not_end_the_command(self):
        commands = [
            "git commit -m 'fix: x' 2>&1 --no-verify", "git commit -m 'fix: x' > log.txt -n",
            "lattice 2>&1 next", "lattice complete 2>/dev/null AA-1",
            "git worktree 2>/dev/null prune",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")


class WorktreeCases(unittest.TestCase):
    def test_prune_is_refused_and_named_worktrees_pass(self):
        for command in ("git worktree prune", "git -c gc.worktreePruneExpire=now gc",
            "git config gc.worktreePruneExpire now", "git -C project worktree prune --expire now",
                        "bash -c 'git worktree prune'"):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")
        for command in ("git worktree list", "git worktree add .worktrees/AA-1 -b feature/AA-1-x main",
                        "git worktree remove .worktrees/AA-1"):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")


class LatticeCases(unittest.TestCase):
    def test_owner_actions_are_refused(self):
        commands = [
            "lattice next", "lattice next --claim --actor agent:claude",
            "lattice complete AA-1 --actor agent:claude",
            "lattice status AA-1 done --actor agent:claude",
            "lattice status AA-1 done --no-auto-review --actor agent:codex",
            "LATTICE_NO_UPDATE_CHECK=1 lattice status AA-1 done --actor agent:claude",
            "lattice comment AA-1 approved --actor human:patrick",
            "lattice comment AA-1 approved --actor=human:patrick",
            "lattice comment AA-1 approved --actor agent:claude --on-behalf-of human:patrick",
            "lattice needs-human AA-1 --clear --note ok --actor Human:patrick",
            "lattice comment AA-1 'Reviewed: abc' --role review --actor agent:claude",
            "lattice comment AA-1 ok --role=plan-review --actor agent:claude",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")

    def test_agent_board_work_passes(self):
        commands = [
            "lattice show AA-1", "lattice comments AA-1 --json", "lattice plan AA-1",
            "lattice status AA-1 in_review --no-auto-review --actor agent:claude",
            "lattice status AA-1 in_progress --actor agent:codex",
            "lattice comment AA-1 'the checks are done' --role validation --actor agent:claude",
            "lattice comment AA-1 done --actor agent:claude",
            "lattice needs-human AA-1 'Need: approve plan' --actor agent:claude",
            "lattice attach AA-1 out.txt --title 'review notes' --actor agent:claude",
            "lattice branch-link AA-1 feature/AA-1-x --actor agent:claude",
            "lattice criterion add AA-1 'The owner sees the done state' --actor agent:claude",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")

    def test_the_refusal_says_what_to_do_instead(self):
        result = subprocess.run(["/usr/bin/python3", "-I", str(GUARD)], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "lattice complete AA-1"}}),
            text=True, capture_output=True, check=True, timeout=10)
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("in_review", reason)
        self.assertNotIn("remote writes", reason)


class GcloudCases(unittest.TestCase):
    def test_only_the_approved_reads_pass(self):
        commands = [
            'gcloud version', 'gcloud --version', 'gcloud -v',
            'gcloud help', 'gcloud --help', 'gcloud -h',
            'gcloud config get-value project',
            'gcloud --configuration list config get-value project',
            'gcloud config --configuration=describe get-value project',
            'gcloud --project=list config get-value project --account describe',
            'gcloud --quiet config get-value project --format=value',
            'gcloud --verbosity info version',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")

    def test_other_operations_and_unsupported_options_are_refused(self):
        commands = [
            'gcloud projects delete list',
            'gcloud auth print-access-token --account list',
            'gcloud --configuration list projects delete describe',
            'gcloud projects delete describe --project=list --account info',
            'gcloud secrets versions access list --secret describe',
            'gcloud config set project list',
            'gcloud config get-value auth/access_token',
            'gcloud projects list', 'gcloud projects describe list',
            'gcloud version --flags-file fake.yaml',
            'gcloud --flags-file=fake.yaml config get-value project',
            'gcloud --credential-file-override=fake.json version',
            'gcloud --account', 'gcloud --project= version',
            'gcloud --unknown list version', 'gcloud --configuration --version',
            'gcloud version projects delete list',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")


class GithubCases(unittest.TestCase):
    def test_rest_api_data_flags_do_not_hide_posts(self):
        for command in ('gh api repos/example/issues -ftitle=example',
                        'gh api repos/example/issues -Ftitle=example',
                        'gh api repos/example/issues --method=POST',
                        'gh api repos/example/issues -XPOST',
                        'gh api repos/example/issues --raw-field=title=example'):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "deny")
        for command in ('gh api repos/example/issues',
                        'gh api repos/example/issues -XGET -fq=example'):
            with self.subTest(command=command):
                self.assertEqual(decision(GUARD, command), "allow")


class HarnessTests(unittest.TestCase):
    def test_bad_decisions_crashes_and_invalid_output_fail_the_process(self):
        fixtures = ["", "raise SystemExit(7)\n", "print('invalid output')\n"]
        with tempfile.TemporaryDirectory() as folder:
            guard = pathlib.Path(folder, "fixture.py")
            for source in fixtures:
                with self.subTest(source=source):
                    guard.write_text(source)
                    result = subprocess.run([sys.executable, __file__, "--case", str(guard), "deny"],
                                            text=True, capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--case"]:
        check_case(pathlib.Path(sys.argv[2]), sys.argv[3])
    else:
        unittest.main()
