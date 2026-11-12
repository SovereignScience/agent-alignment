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
'''
CA_FILE = "/etc/ssl/certs/ca-certificates.crt"
CA_NAMES = ("SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PIP_CERT")
MARK = "# Admin-enforced Codex requirements. Only the profile defined here may run,"
# swe/codex/requirements.toml as 17def8a shipped and installed it.
PREDECESSOR = '''# Admin-enforced Codex requirements for this track, installed as
# /etc/codex/requirements.toml by swe/scripts/install_isolation.sh. Only the
# profiles listed may run, so Full Access and the built-in profiles, which do
# not carry the workstation profile's read denials, are refused. Needs Codex
# 0.138.0 or later. After installing, confirm in both the CLI and the VS Code
# extension that sessions start on workstation and that Full Access is refused.
[allowed_permission_profiles]
"workstation" = true
'''
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
        (self.home / ".codex/attachments").mkdir()
        (self.home / ".codex/skills/openai-docs").mkdir(parents=True)
        self.etc = root / "etc"
        (self.etc / "claude-code").mkdir(parents=True)
        self.local = root / "managed-local.json"
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "sudo").write_text(FAKE_SUDO)
        (self.bin / "sudo").chmod(0o755)
        self.repo = root / "checkout"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        self.git("commit", "-q", "--allow-empty", "-m", "start")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Owner", "-c", "user.email=owner@example.com",
                        *args], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        parent = {key: value for key, value in os.environ.items() if key not in CA_NAMES}
        return dict(parent, HOME=str(self.home), SWE_WORKSPACE=str(self.home / "projects"),
                    SWE_ETC=str(self.etc / "claude-code"), SWE_CODEX_ETC=str(self.etc / "codex"),
                    SWE_MANAGED_LOCAL=str(self.local), PATH="%s:%s" % (self.bin, os.environ["PATH"]),
                    GIT_DIR=str(self.repo / ".git"), **extra)

    def run_installer(self, codex=PROFILE, local=None, user=None, apply=False, cwd=None, **extra):
        if codex is None:
            (self.home / ".codex/config.toml").unlink(missing_ok=True)
        else:
            (self.home / ".codex/config.toml").write_text(codex)
        if local is not None:
            self.local.write_text(json.dumps(local))
        if user is not None:
            (self.home / ".claude/settings.json").write_text(json.dumps(user))
        run = subprocess.run(["bash", str(SCRIPT)] + (["--apply"] if apply else []), env=self.env(**extra),
                             input="y\n", capture_output=True, text=True, timeout=120, cwd=cwd)
        return run.returncode, run.stdout + run.stderr

    preview = run_installer

    def requirements(self):
        return tomllib.loads((self.etc / "codex/requirements.toml").read_text())

    def test_installer_ignores_planted_python_and_modules(self):
        folder = self.home / "projects"
        marker = self.home / "planted-ran"
        module = folder / "json.py"
        interpreter = self.bin / "python3"
        for kind in ("cwd", "pythonpath", "path"):
            with self.subTest(kind=kind):
                try:
                    extra = {}
                    if kind == "path":
                        interpreter.write_text("#!/bin/sh\nprintf ran > " + str(marker) + "\nexit 97\n")
                        interpreter.chmod(0o755)
                    else:
                        module.write_text("from pathlib import Path\nPath(" + repr(str(marker)) +
                                          ").write_text('ran')\nraise SystemExit(97)\n")
                        if kind == "pythonpath":
                            extra["PYTHONPATH"] = str(folder)
                    code, out = self.run_installer(cwd=folder if kind == "cwd" else self.home, **extra)
                    self.assertFalse(marker.exists(), out)
                    self.assertEqual(code, 0, out)
                finally:
                    module.unlink(missing_ok=True)
                    interpreter.unlink(missing_ok=True)
                    marker.unlink(missing_ok=True)

    def test_managed_read_access_keeps_shell_github_and_write_credentials_closed(self):
        code, out = self.run_installer(apply=True, AGENT_GITHUB_READ_TOKEN="made-up-read-token")
        self.assertEqual(code, 0, out)
        req = self.requirements()
        network = req["permissions"]["alignment_workstation"]["network"]
        self.assertTrue(network["enabled"])
        self.assertIs(network["allow_local_binding"], False)
        self.assertFalse(network["enable_socks5"])
        self.assertFalse(network["enable_socks5_udp"])
        self.assertTrue(req["experimental_network"]["enabled"])
        self.assertTrue(req["experimental_network"]["managed_allowed_domains_only"])
        self.assertIs(req["experimental_network"]["allow_local_binding"], False)
        managed = json.loads((self.etc / "claude-code/managed-settings.json").read_text())
        domains = managed["sandbox"]["network"]["allowedDomains"]
        self.assertNotIn("allowLocalBinding", managed["sandbox"]["network"])
        self.assertEqual(req["experimental_network"]["domains"], dict.fromkeys(domains, "allow"))
        self.assertIn("pypi.org", domains)
        self.assertIn("127.0.0.1", domains)
        self.assertIn("localhost", domains)
        for host in ("*", "github.com", "api.github.com", "api.githubcopilot.com",
                     "127.0.0.2", "0.0.0.0", "::1", "10.0.0.1", "169.254.169.254"):
            self.assertNotIn(host, domains)
        endpoint = "https://api.githubcopilot.com/mcp/readonly"
        self.assertEqual(req["mcp_servers"], {"github_read": {"identity": {"url": endpoint}}})
        self.assertEqual(managed["allowedMcpServers"], [{"serverUrl": endpoint}])
        self.assertTrue(managed["allowManagedMcpServersOnly"])
        self.assertIn({"name": "AGENT_GITHUB_READ_TOKEN", "mode": "deny"},
                      managed["sandbox"]["credentials"]["envVars"])
        config = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(config["shell_environment_policy"]["filters"]["AGENT_GITHUB_READ_TOKEN"], "exclude")
        self.assertNotIn("mcp_servers", config)
        self.assertEqual(config["shell_environment_policy"]["inherit"], "core")
        self.assertFalse(config["shell_environment_policy"]["ignore_default_excludes"])
        self.assertEqual(config["shell_environment_policy"].get("set"), {
            "SSL_CERT_FILE": CA_FILE, "REQUESTS_CA_BUNDLE": CA_FILE})
        self.assertEqual(managed["env"]["SSL_CERT_FILE"], CA_FILE)
        self.assertNotIn("made-up-read-token", out)
        fs = req["permissions"]["alignment_workstation"]["filesystem"]
        self.assertEqual(fs["~/.codex/config.toml"], "deny")
        self.assertIn("Read(~/.codex/config.toml)", managed["permissions"]["deny"])
        self.assertIn("~/.codex/config.toml", managed["sandbox"]["filesystem"]["denyRead"])

    def test_token_exclusion_preserves_other_shell_policy(self):
        config = PROFILE + '\n[shell_environment_policy]\ninherit = "none"\n' + (
            '\n[shell_environment_policy.filters]\n"EXAMPLE_TOKEN" = "exclude"\n')
        code, out = self.run_installer(codex=config, apply=True)
        self.assertEqual(code, 0, out)
        updated = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(updated["shell_environment_policy"]["inherit"], "none")
        self.assertEqual(updated["shell_environment_policy"]["filters"], {
            "EXAMPLE_TOKEN": "exclude", "AGENT_GITHUB_READ_TOKEN": "exclude"})

    def test_ca_default_preserves_existing_environment_and_is_idempotent(self):
        config = PROFILE + '\n[shell_environment_policy]\ninherit = "none"\n' + (
            '\n[shell_environment_policy.set]\nKEEP = "made-up-control"\n')
        code, out = self.run_installer(codex=config, apply=True)
        self.assertEqual(code, 0, out)
        first = (self.home / ".codex/config.toml").read_text()
        policy = tomllib.loads(first)["shell_environment_policy"]
        self.assertEqual(policy["inherit"], "none")
        self.assertEqual(policy["set"], {"KEEP": "made-up-control", "SSL_CERT_FILE": CA_FILE,
                                         "REQUESTS_CA_BUNDLE": CA_FILE})
        self.assertEqual(policy["filters"]["AGENT_GITHUB_READ_TOKEN"], "exclude")
        code, out = self.run_installer(codex=first, apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.home / ".codex/config.toml").read_text(), first)

    def test_requests_default_repairs_existing_ssl_file_and_is_idempotent(self):
        config = PROFILE + '\n[shell_environment_policy.set]\nSSL_CERT_FILE = "' + CA_FILE + '"\n'
        code, out = self.run_installer(codex=config, apply=True)
        self.assertEqual(code, 0, out)
        first = (self.home / ".codex/config.toml").read_text()
        self.assertEqual(tomllib.loads(first)["shell_environment_policy"]["set"], {
            "SSL_CERT_FILE": CA_FILE, "REQUESTS_CA_BUNDLE": CA_FILE})
        self.assertIn("set shell_environment_policy.set.REQUESTS_CA_BUNDLE", out)
        code, out = self.run_installer(codex=first, apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.home / ".codex/config.toml").read_text(), first)

    def test_requests_trust_conflicts_stop_with_ssl_file_already_set(self):
        for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT"):
            for inherited in (False, True):
                with self.subTest(name=name, inherited=inherited):
                    value = "/tmp/made-up-custom-requests-store"
                    config = PROFILE + '\n[shell_environment_policy.set]\nSSL_CERT_FILE = "' + CA_FILE + '"\n'
                    extra = {name: value} if inherited else {}
                    if not inherited:
                        config += name + ' = "' + value + '"\n'
                    code, out = self.run_installer(codex=config, apply=True, **extra)
                    self.assertNotEqual(code, 0, out)
                    self.assertIn(name, out)
                    self.assertIn("Nothing was written", out)
                    self.assertNotIn(value, out)
                    self.assertFalse((self.etc / "codex/requirements.toml").exists())
                    self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
                    self.assertEqual((self.home / ".codex/config.toml").read_text(), config)

    def test_requests_explicit_choice_preserves_other_ca_settings(self):
        config = PROFILE + '\n[shell_environment_policy.set]\n' + (
            'SSL_CERT_FILE = "' + CA_FILE + '"\nREQUESTS_CA_BUNDLE = "' + CA_FILE +
            '"\nCURL_CA_BUNDLE = "/tmp/made-up-curl-store"\n')
        code, out = self.run_installer(codex=config, apply=True,
                                       REQUESTS_CA_BUNDLE="/tmp/made-up-inherited-store")
        self.assertEqual(code, 0, out)
        updated = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(updated["shell_environment_policy"]["set"], {
            "SSL_CERT_FILE": CA_FILE, "REQUESTS_CA_BUNDLE": CA_FILE,
            "CURL_CA_BUNDLE": "/tmp/made-up-curl-store"})

    def test_instruction_table_headers_stop_before_installed_writes(self):
        for table in ("shell_environment_policy", "shell_environment_policy.filters",
                      "shell_environment_policy.set"):
            for apply in (False, True):
                with self.subTest(table=table, apply=apply):
                    config = "developer_instructions = '''\n[" + table + "]\n'''\n" + PROFILE
                    code, out = self.run_installer(codex=config, apply=apply)
                    self.assertNotEqual(code, 0, out)
                    self.assertIn("could not safely set", out)
                    self.assertFalse((self.etc / "codex/requirements.toml").exists())
                    self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
                    self.assertEqual((self.home / ".codex/config.toml").read_text(), config)

    def test_custom_ca_settings_stop_before_installed_writes(self):
        cases = [(name, "/tmp/made-up-custom-trust-store") for name in CA_NAMES]
        cases.append(("SSL_CERT_DIR", ""))
        for name, value in cases:
            with self.subTest(name=name, empty=not value):
                config = PROFILE + '\n[shell_environment_policy.set]\n' + name + ' = "' + value + '"\n'
                code, out = self.run_installer(codex=config, apply=True)
                self.assertNotEqual(code, 0, out)
                self.assertIn(name, out)
                self.assertIn("Nothing was written", out)
                if value:
                    self.assertNotIn(value, out)
                self.assertFalse((self.etc / "codex/requirements.toml").exists())
                self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
                self.assertEqual((self.home / ".codex/config.toml").read_text(), config)

    def test_inherited_custom_ca_settings_stop_before_installed_writes(self):
        for name in CA_NAMES:
            with self.subTest(name=name):
                value = "/tmp/made-up-inherited-trust-store"
                code, out = self.run_installer(apply=True, **{name: value})
                self.assertNotEqual(code, 0, out)
                self.assertIn(name, out)
                self.assertIn("Nothing was written", out)
                if value:
                    self.assertNotIn(value, out)
                self.assertFalse((self.etc / "codex/requirements.toml").exists())
                self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
                self.assertEqual((self.home / ".codex/config.toml").read_text(), PROFILE)

    def test_commented_filter_header_without_final_newline(self):
        code, out = self.run_installer(codex=PROFILE + '\n[shell_environment_policy.filters] # keep', apply=True)
        self.assertEqual(code, 0, out)
        config = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(config["shell_environment_policy"]["filters"]["AGENT_GITHUB_READ_TOKEN"], "exclude")

    def test_conflicting_token_filters_stop_before_writes(self):
        for policy in ('[shell_environment_policy]\nexclude = ["OTHER"]\n',
                       '[shell_environment_policy]\nfilters = { OTHER = "exclude" }\n',
                       '[shell_environment_policy.filters]\n"AGENT_GITHUB_READ_TOKEN" = "include"\n',
                       '[shell_environment_policy.filters]\n"agent_github_read_token" = "include"\n',
                       '[shell_environment_policy]\nset = { AGENT_GITHUB_READ_TOKEN = "made-up-restored" }\n',
                       '[shell_environment_policy]\ninherit = "all"\n',
                       '[shell_environment_policy]\nignore_default_excludes = true\n'):
            with self.subTest(policy=policy):
                code, out = self.run_installer(codex=PROFILE + "\n" + policy, apply=True)
                self.assertNotEqual(code, 0, out)
                self.assertIn("Nothing was written", out)
                self.assertFalse((self.etc / "codex/requirements.toml").exists())
                self.assertNotIn("made-up-restored", out)

    def test_a_codex_config_the_admin_profile_cannot_follow_stops_the_preview(self):
        for config in (PROFILE.replace('"workstation"', '":danger-full-access"', 1),
                       PROFILE + '\n[permissions.alignment_workstation]\nextends = ":workspace"\n',
                       None):
            with self.subTest(config=config):
                code, out = self.preview(codex=config)
                self.assertNotEqual(code, 0, out)
                self.assertIn("Nothing was written", out)

    def test_the_profile_skips_denials_codex_cannot_apply(self):
        (self.home / ".ssh").mkdir()
        (self.home / "elsewhere").mkdir()
        (self.home / ".aws").symlink_to(self.home / ".ssh")
        (self.home / ".kube").symlink_to(self.home / "elsewhere")
        (self.home / ".gitconfig").write_text("")
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        req = self.requirements()
        self.assertEqual(req["default_permissions"], "alignment_workstation")
        self.assertEqual(req["allowed_permission_profiles"], {"alignment_workstation": True})
        self.assertIs(req["allow_managed_hooks_only"], True)
        self.assertEqual(req["mcp_servers"], {"github_read": {"identity": {"url": "https://api.githubcopilot.com/mcp/readonly"}}})
        self.assertEqual(req["features"], {"plugins": False, "apps": False})
        fs = req["permissions"]["alignment_workstation"]["filesystem"]
        self.assertEqual(fs["~/.ssh"], "deny")
        self.assertEqual(fs[str(self.home / "elsewhere")], "deny")
        self.assertNotIn("~/.aws", fs)
        self.assertNotIn("~/.kube", fs)
        self.assertNotIn("~/.netrc", fs)
        self.assertEqual(fs["glob_scan_max_depth"], 8)
        self.assertEqual(fs[":workspace_roots"]["**/.env"], "deny")
        self.assertEqual(fs[":root"], "deny")
        self.assertEqual(fs[":minimal"], "read")
        self.assertEqual(fs["~/.gitconfig"], "read")
        self.assertNotIn("~/.config/git", fs)
        self.assertIn("~/.config/git (does not exist)", out)
        self.assertIn("~/.aws (links into a denied folder)", out)
        self.assertIn("~/.netrc (does not exist)", out)
        config = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(config["default_permissions"], "alignment_workstation")

    def test_a_reopen_never_overrides_a_denial(self):
        (self.home / ".config/git").mkdir(parents=True)
        (self.home / ".config/git/credentials").write_text("made-up")
        code, out = self.run_installer(local={"sandbox": {"filesystem": {"denyRead": ["~/.config", "/etc"]}}},
                                       apply=True)
        self.assertEqual(code, 0, out)
        fs = self.requirements()["permissions"]["alignment_workstation"]["filesystem"]
        self.assertEqual(fs["~/.config"], "deny")
        self.assertNotIn("~/.config/git", fs)
        self.assertEqual(fs["/etc"], "deny")
        self.assertIn("~/.config/git (at or under a denied path)", out)
        self.assertIn("/etc (at or under a denied path)", out)

    def test_codex_inputs_are_read_only_without_opening_codex_home(self):
        (self.home / ".codex/auth.json").write_text("made-up")
        (self.home / ".codex/sessions").mkdir()
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        req = self.requirements()
        fs = req["permissions"]["alignment_workstation"]["filesystem"]
        self.assertEqual(fs["~/.codex/attachments"], "read")
        self.assertEqual(fs["~/.codex/skills/openai-docs"], "read")
        self.assertNotIn("~/.codex", fs)
        self.assertNotIn(str(self.home), fs)
        self.assertEqual(fs["~/.codex/auth.json"], "deny")
        self.assertEqual(fs["~/.codex/sessions"], "deny")
        self.assertEqual(fs[":root"], "deny")
        self.assertTrue(req["permissions"]["alignment_workstation"]["network"]["enabled"])
        self.assertEqual(req["allowed_permission_profiles"], {"alignment_workstation": True})
        self.assertEqual(req["mcp_servers"], {"github_read": {"identity": {"url": "https://api.githubcopilot.com/mcp/readonly"}}})

    def test_codex_input_reopens_preserve_explicit_denials(self):
        for path in ("~/.codex", "~/.codex/attachments", "~/.codex/skills/openai-docs"):
            with self.subTest(path=path):
                code, out = self.run_installer(
                    local={"sandbox": {"filesystem": {"denyRead": [path]}}}, apply=True)
                self.assertEqual(code, 0, out)
                fs = self.requirements()["permissions"]["alignment_workstation"]["filesystem"]
                self.assertEqual(fs[path], "deny")
                for read in ("~/.codex/attachments", "~/.codex/skills/openai-docs"):
                    if read == path or read.startswith(path + "/"):
                        self.assertNotEqual(fs.get(read), "read")

    def test_printed_undo_restores_requirements_without_input_grants(self):
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        path = self.etc / "codex/requirements.toml"
        before = path.read_text().replace('"~/.codex/attachments" = "read"\n', "").replace(
            '"~/.codex/skills/openai-docs" = "read"\n', "")
        path.write_text(before)
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.requirements()["permissions"]["alignment_workstation"]
                         ["filesystem"]["~/.codex/attachments"], "read")
        undo = [line.strip() for line in out.split("To undo, run:\n", 1)[1].splitlines()
                if line.startswith("  sudo cp -a ") and line.endswith(" " + str(path))]
        self.assertEqual(len(undo), 1, out)
        subprocess.run(["bash", "-c", undo[0]], env=self.env(), check=True)
        self.assertEqual(path.read_text(), before)

    def test_missing_optional_codex_inputs_are_reported_without_a_grant(self):
        for path in ("attachments", "skills/openai-docs"):
            (self.home / ".codex" / path).rmdir()
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        self.assertIn("~/.codex/attachments (does not exist)", out)
        self.assertIn("~/.codex/skills/openai-docs (does not exist)", out)
        fs = self.requirements()["permissions"]["alignment_workstation"]["filesystem"]
        self.assertNotIn("~/.codex/attachments", fs)
        self.assertNotIn("~/.codex/skills/openai-docs", fs)

    def test_unsafe_codex_input_roots_stop_before_policy_writes(self):
        for name in ("attachments", "skills/openai-docs"):
            path = self.home / ".codex" / name
            for kind in ("file", "symlink", "broken_symlink"):
                with self.subTest(name=name, kind=kind):
                    path.rmdir()
                    if kind == "file":
                        path.write_text("made-up")
                    elif kind == "symlink":
                        path.symlink_to(self.home)
                    else:
                        path.symlink_to(self.home / "missing")
                    try:
                        code, out = self.run_installer(apply=True)
                        self.assertNotEqual(code, 0, out)
                        self.assertIn("must be an existing directory without symlink components", out)
                        self.assertIn("Nothing was written", out)
                        self.assertFalse((self.etc / "codex/requirements.toml").exists())
                    finally:
                        path.unlink()
                        path.mkdir()

    def test_aliased_codex_input_parent_is_not_reopened(self):
        parent = self.home / ".codex/skills"
        shutil.rmtree(parent)
        other = self.home / "other-skills"
        (other / "openai-docs").mkdir(parents=True)
        parent.symlink_to(other)
        code, out = self.run_installer(apply=True)
        self.assertNotEqual(code, 0, out)
        self.assertIn("must be an existing directory without symlink components", out)
        self.assertFalse((self.etc / "codex/requirements.toml").exists())

    def test_a_reopen_under_a_symlinked_denial_is_left_out(self):
        (self.home / "protected/git").mkdir(parents=True)
        (self.home / "protected/git/private-settings.txt").write_text("made-up")
        (self.home / ".config").symlink_to(self.home / "protected")
        code, out = self.run_installer(local={"sandbox": {"filesystem": {"denyRead": ["~/.config"]}}}, apply=True)
        self.assertEqual(code, 0, out)
        fs = self.requirements()["permissions"]["alignment_workstation"]["filesystem"]
        self.assertEqual(fs[str(self.home / "protected")], "deny")
        self.assertEqual([k for k in fs if k.endswith("/git")], [])
        self.assertIn("~/.config/git (at or under a denied path)", out)

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

    def test_only_requirements_this_script_wrote_are_replaced(self):
        (self.etc / "codex").mkdir()
        requirements = self.etc / "codex/requirements.toml"
        requirements.write_text('[allowed_permission_profiles]\n"other" = true\n')
        code, out = self.preview()
        self.assertNotEqual(code, 0, out)
        self.assertIn("holds policy this script did not write", out)
        requirements.write_text(MARK + "\n# an older run\n")
        code, out = self.preview()
        self.assertEqual(code, 0, out)
        self.assertIn("== %s" % requirements, out)
        requirements.write_text(PREDECESSOR)
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.requirements()["default_permissions"], "alignment_workstation")
        self.assertEqual([b.read_text() for b in requirements.parent.glob("requirements.toml.*.bak")], [PREDECESSOR])

    def test_without_codex_the_admin_requirements_are_left_alone(self):
        shutil.rmtree(self.home / ".codex")
        code, out = self.preview(codex=None)
        self.assertEqual(code, 0, out)
        self.assertIn("note: no ~/.codex", out)
        self.assertNotIn(str(self.etc / "codex/requirements.toml"), out)

    def test_invalid_local_entries_are_refused(self):
        for local in ({"permissions": {"deny": [123]}},
                      {"permissions": {"deny": [""]}},
                      {"sandbox": {"filesystem": {}}},
                      {"sandbox": {"credentials": {"files": [{"path": "~/.x", "mode": "mask"}]}}},
                      {"sandbox": {"credentials": {"files": [{"path": "", "mode": "deny"}]}}},
                      {"sandbox": {"filesystem": {"allowRead": ["~/miniconda3"]}}},
                      {"sandbox": {"filesystem": {"allowWrite": ["~/"]}}}):
            with self.subTest(local=local):
                code, out = self.preview(local=local)
                self.assertNotEqual(code, 0, out)

    def test_every_managed_hook_starts_with_an_absolute_interpreter(self):
        managed = json.loads((SCRIPT.parent.parent / ".claude/managed-settings.example.json").read_text())
        commands = [h["command"] for event in managed["hooks"].values() for entry in event for h in entry["hooks"]]
        self.assertTrue(commands)
        for command in commands:
            self.assertTrue(command.startswith("/"), command)

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
        (self.home / 'odd"name').write_text("")
        sentinel = self.home / ".config/agent-alignment/sentinel"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("")
        code, out = self.preview(local={"sandbox": {"filesystem": {"denyRead": ['~/odd"name']}}})
        self.assertEqual(code, 0, out)
        self.assertIn('"~/odd\\"name" = "deny"', out)
        self.assertIn("write      %s/.cache-agent" % self.home, out)
        self.assertIn("write      %s" % sentinel, out)

    def test_apply_installs_and_the_printed_undo_restores_every_file(self):
        user = {"permissions": {"deny": ["Read(**/*token*)", "Read(**/credentials)",
                                           "Read(~/project-private/**)", "Bash(git push *)"]}}
        code, out = self.run_installer(user=user, apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.requirements()["default_permissions"], "alignment_workstation")
        self.assertEqual(json.loads((self.home / ".claude/settings.json").read_text())["permissions"]["deny"],
                         ["Read(~/project-private/**)", "Bash(git push *)"])
        self.assertIn("remove permissions.deny Read(**/credentials)", out)
        managed = json.loads((self.etc / "claude-code/managed-settings.json").read_text())
        for path in ("~/.cargo/credentials", "~/.cargo/credentials.toml", "~/.config/git/credentials"):
            self.assertIn("Read(%s)" % path, managed["permissions"]["deny"])
            self.assertIn(path, managed["sandbox"]["filesystem"]["denyRead"])
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", managed["env"])
        self.assertNotIn("~/", managed["sandbox"]["filesystem"]["denyRead"])
        self.assertTrue((self.etc / "claude-code/hooks/guard_outward.py").is_file())
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

    def test_apply_refuses_a_checkout_whose_head_does_not_contain_main(self):
        self.git("branch", "older")
        self.git("commit", "-q", "--allow-empty", "-m", "newer rules")
        self.git("checkout", "-q", "older")
        code, out = self.run_installer(apply=True)
        self.assertEqual(code, 1, out)
        self.assertIn("this checkout's HEAD does not contain main", out)
        self.assertFalse((self.etc / "claude-code/managed-settings.json").exists())
        self.assertEqual(self.preview()[0], 0)

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
