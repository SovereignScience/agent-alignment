"""install_isolation.sh against a made-up home and /etc, with a fake sudo. Nothing real is read or written.

Run: python3 -m unittest discover -s swe/scripts -p 'test_*.py'
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import tomllib
import unittest

SCRIPT = pathlib.Path(__file__).with_name("install_isolation.sh")
PROFILE = '''default_permissions = "workstation"

[permissions.workstation]
extends = ":workspace"

[permissions.workstation.filesystem]
"~/.ssh" = "deny"
'''
ROOTS = '\n[permissions.workstation.filesystem.":workspace_roots"]\n'
# Runs the command as the current user, without install's root ownership flags.
# FAKE_SUDO_FAIL makes any command naming a path with that ending fail.
FAKE_SUDO = '''#!/usr/bin/env bash
args=()
while [ "$#" -gt 0 ]; do
    case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac
done
if [ -n "${FAKE_SUDO_FAIL:-}" ]; then
    for a in "${args[@]}"; do case "$a" in *"$FAKE_SUDO_FAIL") exit 1 ;; esac; done
fi
exec "${args[@]}"
'''


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.home = root / "home"
        (self.home / "projects").mkdir(parents=True)
        (self.home / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        self.etc = root / "etc"
        (self.etc / "claude-code").mkdir(parents=True)
        self.local = root / "managed-local.json"
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "sudo").write_text(FAKE_SUDO)
        (self.bin / "sudo").chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        return dict(os.environ, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                    SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                    SWE_MANAGED_LOCAL=str(self.local), PATH="%s:%s" % (self.bin, os.environ["PATH"]),
                    **extra)

    def run_installer(self, codex=PROFILE, local=None, user=None, apply=False, **extra):
        if codex is None:
            (self.home / ".codex/config.toml").unlink(missing_ok=True)
        else:
            (self.home / ".codex/config.toml").write_text(codex)
        if local is not None:
            self.local.write_text(json.dumps(local))
        if user is not None:
            (self.home / ".claude/settings.json").write_text(json.dumps(user))
        run = subprocess.run(["bash", str(SCRIPT)] + (["--apply"] if apply else []), env=self.env(**extra),
                             input="y\n", capture_output=True, text=True, timeout=120)
        return run.returncode, run.stdout + run.stderr

    preview = run_installer

    def test_a_conflicting_codex_grant_stops_the_preview(self):
        code, out = self.preview(codex=PROFILE + '"~/.vault-token" = "read"\n')
        self.assertNotEqual(code, 0, out)
        self.assertIn('"~/.vault-token" = "read"', out)
        self.assertIn("Nothing was written", out)

    def test_a_profile_that_does_more_than_the_snippet_stops_the_preview(self):
        for config in ('default_permissions = "workstation"\n',
                       PROFILE.replace('default_permissions = "workstation"', 'default_permissions = ":workspace"'),
                       PROFILE.replace('extends = ":workspace"', 'extends = ":danger-full-access"'),
                       PROFILE + '"~/.cache" = "write"\n',
                       PROFILE + ROOTS + '"**/.env" = "read"\n',
                       PROFILE + '\n[permissions.workstation.network]\nenabled = true\n',
                       PROFILE + '\n[permissions.workstation.workspace_roots]\n"~" = true\n',
                       PROFILE + 'glob_scan_max_depth = 2\n',
                       None):
            with self.subTest(config=config):
                code, out = self.preview(codex=config)
                self.assertNotEqual(code, 0, out)
                self.assertIn("Nothing was written", out)

    def test_unsafe_targets_or_managed_directories_stop_the_preview(self):
        real = self.home / "settings-real.json"
        real.write_text("{}")
        (self.home / ".claude/settings.json").symlink_to(real)
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("symlink", out)
        (self.home / ".claude/settings.json").unlink()

        hooks = self.etc / "claude-code/hooks"
        writable = self.home / "writable-hooks"
        writable.mkdir()
        hooks.symlink_to(writable)
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("%s is a symlink" % hooks, out)
        hooks.unlink()

        hooks.mkdir()
        hooks.chmod(0o777)
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("writable by group or others", out)
        hooks.chmod(0o755)

        (self.etc / "claude-code/managed-settings.json").mkdir()
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("not a regular file", out)
        (self.etc / "claude-code/managed-settings.json").rmdir()

        (self.etc / "codex").mkdir()
        (self.etc / "codex/requirements.toml").write_text('[allowed_permission_profiles]\n"other" = true\n')
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("already holds other policy", out)

    def test_without_codex_the_admin_requirements_are_left_alone(self):
        shutil.rmtree(self.home / ".codex")
        code, out = self.preview(codex=None)
        self.assertEqual(code, 0, out)
        self.assertIn("note: no ~/.codex", out)
        self.assertNotIn(str(self.etc / "codex/requirements.toml"), out)

    def test_entries_already_denied_are_not_added_again(self):
        code, out = self.preview(codex=PROFILE + 'glob_scan_max_depth = 12\n' + ROOTS + '"**/.env" = "deny"\n')
        self.assertEqual(code, 0, out)
        self.assertNotIn("add glob_scan_max_depth", out)
        self.assertNotIn('add "~/.ssh" = "deny"', out)
        self.assertIn('add "~/.claude" = "deny"', out)
        self.assertNotIn('add [":workspace_roots"] "**/.env"', out)
        self.assertIn('add [":workspace_roots"] "**/*.tfvars" = "deny"', out)

    def test_invalid_local_entries_are_refused(self):
        for local in ({"permissions": {"deny": [123]}},
                      {"permissions": {"deny": [""]}},
                      {"sandbox": {"filesystem": {}}},
                      {"sandbox": {"credentials": {"files": [{"path": "~/.x", "mode": "mask"}]}}},
                      {"sandbox": {"credentials": {"files": [{"path": "", "mode": "deny"}]}}},
                      {"sandbox": {"filesystem": {"allowWrite": ["~/"]}}}):
            with self.subTest(local=local):
                code, out = self.preview(local=local)
                self.assertNotEqual(code, 0, out)

    def test_the_preview_never_prints_setting_values(self):
        user = {"env": {"EXAMPLE_API_KEY": "made-up-user-value"},
                "permissions": {"deny": ["Read(**/*token*)"], "additionalDirectories": [str(self.home)]}}
        codex = PROFILE + '\n[mcp_servers.example.env]\nTOKEN = "made-up-codex-value"\n'
        (self.etc / "claude-code/managed-settings.json").write_text(json.dumps(
            {"apiKeyHelper": "made-up-helper-value", "env": {"X": "made-up-env-value"},
             "permissions": {"deny": ["Bash(git push *)"]}}))
        code, out = self.preview(codex=codex, user=user)
        self.assertEqual(code, 0, out)
        for value in ("made-up-user-value", "made-up-codex-value", "made-up-helper-value", "made-up-env-value"):
            self.assertNotIn(value, out)
        self.assertIn("remove permissions.deny Read(**/*token*)", out)
        self.assertIn("warning:", out)

    def test_local_paths_are_escaped_and_prerequisites_listed(self):
        sentinel = self.home / ".config/agent-alignment/sentinel"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("")
        code, out = self.preview(local={"sandbox": {"filesystem": {"denyRead": ['~/odd"name']}}})
        self.assertEqual(code, 0, out)
        self.assertIn('add "~/odd\\"name" = "deny"', out)
        self.assertIn("write      %s/.cache-agent" % self.home, out)
        self.assertIn("write      %s" % sentinel, out)

    def test_apply_installs_and_the_printed_undo_restores_every_file(self):
        user = {"permissions": {"deny": ["Read(**/*token*)", "Bash(git push *)"]}}
        code, out = self.run_installer(user=user, apply=True)
        self.assertEqual(code, 0, out)
        config = tomllib.loads((self.home / ".codex/config.toml").read_text())
        fs = config["permissions"]["workstation"]["filesystem"]
        self.assertEqual(fs["~/.claude"], "deny")
        self.assertEqual(fs[":workspace_roots"]["**/.env"], "deny")
        self.assertEqual(fs["glob_scan_max_depth"], 8)
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text())["permissions"]["deny"],
                         ["Bash(git push *)"])
        self.assertTrue((self.etc / "claude-code/hooks/guard_outward.py").is_file())
        self.assertTrue((self.etc / "codex/requirements.toml").is_file())
        sentinel = self.home / ".config/agent-alignment/sentinel"
        self.assertIn("agent-alignment sentinel", sentinel.read_text())

        undo = [line for line in out.split("To undo, run:\n", 1)[1].splitlines() if line.startswith("  ")]
        self.assertEqual(len(undo), 8, out)
        for command in undo:
            subprocess.run(["bash", "-c", command.strip()], env=self.env(), check=True)
        self.assertEqual((self.home / ".codex/config.toml").read_text(), PROFILE)
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text()), user)
        self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
        self.assertFalse((self.etc / "codex/requirements.toml").exists())

    def test_a_managed_file_with_the_right_content_but_wrong_mode_is_reinstalled(self):
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        guard = self.etc / "claude-code/hooks/guard_outward.py"
        guard.chmod(0o777)
        code, out = self.preview()
        self.assertEqual(code, 0, out)
        self.assertNotIn("unchanged  %s" % guard, out)
        self.assertIn("same content, but owner uid %d, mode 777" % os.getuid(), out)
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(guard.stat().st_mode & 0o7777, 0o755)

    def test_a_failed_write_stops_and_names_what_changed(self):
        user = {"permissions": {"deny": ["Read(**/*token*)"]}}
        code, out = self.run_installer(user=user, apply=True, FAKE_SUDO_FAIL="fetch_allow.txt")
        self.assertNotEqual(code, 0, out)
        self.assertIn("Stopped while installing %s/claude-code/hooks/fetch_allow.txt" % self.etc, out)
        self.assertIn("Installed 4 of", out)
        self.assertFalse((self.etc / "codex/requirements.toml").exists())
        self.assertEqual((self.home / ".codex/config.toml").read_text(), PROFILE)
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text()), user)


if __name__ == "__main__":
    unittest.main()
