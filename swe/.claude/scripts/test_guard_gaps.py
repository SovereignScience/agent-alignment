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
