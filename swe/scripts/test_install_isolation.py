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
        if codex is not None:
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

    def test_a_missing_profile_table_or_default_stops_the_preview(self):
        for config in ('default_permissions = "workstation"\n',
                       PROFILE.replace('default_permissions = "workstation"', 'default_permissions = ":workspace"')):
            code, out = self.preview(codex=config)
            self.assertNotEqual(code, 0, out)

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
        code, out = self.preview(codex=codex, user=user)
        self.assertEqual(code, 0, out)
        self.assertNotIn("made-up-user-value", out)
        self.assertNotIn("made-up-codex-value", out)
        self.assertIn("remove permissions.deny Read(**/*token*)", out)
        self.assertIn("warning:", out)


if __name__ == "__main__":
    unittest.main()
