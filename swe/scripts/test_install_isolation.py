"""install_isolation.sh previews against a made-up home and /etc. Nothing real is read or written.

Run: python3 -m unittest discover -s swe/scripts -p 'test_*.py'
"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("install_isolation.sh")
PROFILE = '''default_permissions = "workstation"

[permissions.workstation]
extends = ":workspace"

[permissions.workstation.filesystem]
"~/.ssh" = "deny"
'''


class Preview(unittest.TestCase):
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

    def tearDown(self):
        self.tmp.cleanup()

    def preview(self, codex=PROFILE, local=None, user=None):
        if codex is None:
            (self.home / ".codex/config.toml").unlink(missing_ok=True)
        else:
            (self.home / ".codex/config.toml").write_text(codex)
        if local is not None:
            self.local.write_text(json.dumps(local))
        if user is not None:
            (self.home / ".claude/settings.json").write_text(json.dumps(user))
        env = dict(os.environ, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                   SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                   SWE_MANAGED_LOCAL=str(self.local))
        run = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
        return run.returncode, run.stdout + run.stderr

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
                       PROFILE + '\n[permissions.workstation.filesystem.":workspace_roots"]\n"**/.env" = "read"\n',
                       PROFILE + '\n[permissions.workstation.network]\nenabled = true\n',
                       None):
            with self.subTest(config=config):
                code, out = self.preview(codex=config)
                self.assertNotEqual(code, 0, out)
                self.assertIn("Nothing was written", out)

    def test_a_symlinked_target_or_other_codex_policy_stops_the_preview(self):
        real = self.home / "settings-real.json"
        real.write_text("{}")
        (self.home / ".claude/settings.json").symlink_to(real)
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("symlink", out)
        (self.home / ".claude/settings.json").unlink()
        (self.etc / "codex").mkdir()
        (self.etc / "codex/requirements.toml").write_text('[allowed_permission_profiles]\n"other" = true\n')
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("already holds other policy", out)

    def test_entries_already_denied_are_not_added_again(self):
        code, out = self.preview()
        self.assertEqual(code, 0, out)
        self.assertNotIn('add "~/.ssh" = "deny"', out)
        self.assertIn('add "~/.claude" = "deny"', out)

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

    def test_local_paths_are_escaped_and_missing_prerequisites_listed(self):
        code, out = self.preview(local={"sandbox": {"filesystem": {"denyRead": ['~/odd"name']}}})
        self.assertEqual(code, 0, out)
        self.assertIn('add "~/odd\\"name" = "deny"', out)
        self.assertIn("create     %s/.cache-agent" % self.home, out)
        self.assertIn("create     %s/.config/agent-alignment/sentinel" % self.home, out)


if __name__ == "__main__":
    unittest.main()
