"""board_setup.sh against throwaway repositories, a bare remote and the real lattice command."""
import base64
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
import wsgiref.simple_server

SCRIPT = pathlib.Path(__file__).with_name("board_setup.sh")
BASH = shutil.which("bash")
CREDENTIALS = '[credential]\n\thelper = "!f() { echo username=u; echo password=pw; }; f"\n'


class Quiet(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("lattice"), "lattice is not installed")
class BoardSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name, "home")
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = dict(os.environ, HOME=str(self.home), LATTICE_NO_UPDATE_CHECK="1")
        self.env.pop("LATTICE_ROOT", None)
        self.repo = self.project("one")
        self.remote = pathlib.Path(self.tmp.name, "board.git")
        self.git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=self.tmp.name)

    def project(self, parent):
        repo = pathlib.Path(self.tmp.name, parent, "demo-project")
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", cwd=repo)
        (repo / "README.md").write_text("demo\n")
        self.git("add", "README.md", cwd=repo)
        self.git("commit", "-q", "-m", "add readme", cwd=repo)
        return repo

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True,
                              check=True).stdout.strip()

    def serve(self, password=None):
        """Serve the bare remote over smart HTTPS; with a password, only to user u."""
        def app(environ, start_response):
            if password and environ.get("HTTP_AUTHORIZATION") != "Basic " + base64.b64encode(
                    ("u:" + password).encode()).decode():
                start_response("401 Unauthorized", [("WWW-Authenticate", 'Basic realm="git"')])
                return [b""]
            cgi = {name: environ.get(name, "") for name in (
                "REQUEST_METHOD", "PATH_INFO", "QUERY_STRING", "CONTENT_TYPE", "CONTENT_LENGTH", "HTTP_CONTENT_ENCODING")}
            cgi.update(PATH=os.environ["PATH"], GIT_PROJECT_ROOT=self.tmp.name, GIT_HTTP_EXPORT_ALL="1",
                       REMOTE_USER="u" if password else "")
            body = environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0))
            out = subprocess.run(["git", "http-backend"], input=body, env=cgi, capture_output=True).stdout
            head, _, rest = out.partition(b"\r\n\r\n")
            headers = [tuple(line.split(": ", 1)) for line in head.decode().split("\r\n")]
            status = next((v for k, v in headers if k.lower() == "status"), "200 OK")
            start_response(status, [(k, v) for k, v in headers if k.lower() != "status"])
            return [rest]
        if not hasattr(self, "tls"):
            if not shutil.which("openssl"):
                self.skipTest("openssl is not installed")
            self.tls = pathlib.Path(self.tmp.name, "tls.crt")
            self.tls.write_text(subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                 "-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                 "-keyout", "/dev/stdout", "-out", "/dev/stdout"], capture_output=True, text=True, check=True).stdout)
            self.env.update(GIT_SSL_CAINFO=str(self.tls), NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        server = wsgiref.simple_server.make_server("127.0.0.1", 0, app, handler_class=Quiet)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.tls)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "https://127.0.0.1:%d/board.git" % server.server_port

    def run_script(self, *args, cwd=None):
        run = subprocess.run([BASH, str(SCRIPT), *args], cwd=cwd or self.repo, env=self.env, capture_output=True,
                             text=True, timeout=120)
        return run.returncode, run.stdout + run.stderr

    def test_a_project_with_no_board_gets_one_and_no_tracked_file_changes(self):
        code, out = self.run_script("--actor", "human:owner")
        self.assertEqual(code, 0, out)
        config = json.loads((self.repo / ".lattice/config.json").read_text())
        self.assertRegex(out, r"READY: board DP \(demo-project\), review page port %d, new, remote none" % config["dashboard_port"])
        self.assertEqual((config["project_code"], config["default_actor"], config["plan_approval"]), ("DP", "human:owner", "human"))
        self.assertEqual((config["auto_code_review_on_transition"], config["auto_plan_review_on_transition"]), (False, False))
        context = (self.repo / ".lattice/context.md").read_text()
        self.assertTrue(context.startswith("# demo-project\n"))
        self.assertIn("Task: DP-<n>", context)
        self.assertIn("http://127.0.0.1:%d" % config["dashboard_port"], context)
        self.assertIn("The integration branch is main.", context)
        self.assertIn("LATTICE_ROOT=%s set" % str(self.repo).replace(str(self.home), "~", 1), context)
        for left in ("<name>", "<project>", "<path>", "<CODE>", "<port>", "<branch>", "<board directory>"):
            self.assertNotIn(left, context)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.repo / ".git/info/exclude").read_text().splitlines()[-2:], [".lattice/", "/.worktrees/"])
        board = self.repo / ".lattice"
        self.assertEqual(self.git("log", "--format=%an %s", cwd=board), "Owner chore(board): start the board")
        self.assertEqual(self.git("status", "--porcelain", cwd=board), "")
        self.assertIn("context.md", self.git("ls-files", cwd=board).splitlines())

    def test_a_project_that_has_a_board_is_refused_and_left_alone(self):
        self.assertEqual(self.run_script()[0], 0)
        before = self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice")
        code, out = self.run_script()
        self.assertEqual(code, 1)
        self.assertIn("already has a board", out)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice"), before)

    def test_a_new_board_is_pushed_and_comes_back_in_another_checkout(self):
        with open(self.home / ".gitconfig", "a") as config:
            config.write(CREDENTIALS)
        code, out = self.run_script("--remote", self.serve(password="pw"))
        self.assertEqual(code, 0, out)
        pushed = self.git("rev-parse", "main", cwd=self.remote)
        self.assertEqual(pushed, self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice"))
        other = self.project("two")
        code, out = self.run_script("--remote", str(self.remote), cwd=other)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"READY: board DP \(demo-project\), review page port \d+, brought back, remote ")
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=other / ".lattice"), pushed)
        self.assertEqual(self.git("log", "--oneline", cwd=other / ".lattice").count("\n"), 0)
        self.assertEqual(self.git("status", "--porcelain", cwd=other), "")

    def test_a_remote_anyone_can_read_is_refused_before_anything_is_made(self):
        code, out = self.run_script("--remote", self.serve())
        self.assertEqual(code, 1, out)
        self.assertIn("can be read without signing in", out)
        self.assertFalse((self.repo / ".lattice").exists(), out)
        self.assertNotIn(".lattice/", (self.repo / ".git/info/exclude").read_text())
        self.assertEqual(self.git("for-each-ref", cwd=self.remote), "")

    def test_a_private_remote_gets_the_board_and_the_check_never_signs_in(self):
        with open(self.home / ".gitconfig", "a") as config:
            config.write(CREDENTIALS)
        url = self.serve(password="pw")
        code, out = self.run_script("--remote", url)
        self.assertEqual(code, 0, out)
        self.assertIn("new, remote " + url, out)
        self.assertEqual(self.git("rev-parse", "main", cwd=self.remote),
                         self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice"))

    def test_a_proxy_that_asks_for_a_password_is_not_taken_for_a_private_remote(self):
        url = self.serve()
        with open(self.home / ".gitconfig", "a") as config:
            config.write(CREDENTIALS)
        self.env.update(https_proxy="http://user@127.0.0.1:9", HTTPS_PROXY="http://user@127.0.0.1:9")
        code, out = self.run_script("--remote", url)
        self.assertEqual(code, 1, out)
        self.assertIn("cannot check that %s is private" % url, out)
        self.assertFalse((self.repo / ".lattice").exists(), out)
        self.assertEqual(self.git("for-each-ref", cwd=self.remote), "")

    def test_a_remote_it_cannot_check_is_refused(self):
        url = self.serve(password="pw")
        del self.env["GIT_SSL_CAINFO"]
        with open(self.home / ".gitconfig", "a") as config:
            config.write(CREDENTIALS + "[http]\n\tsslCAInfo = %s\n" % self.tls)
        code, out = self.run_script("--remote", url)
        self.assertEqual(code, 1, out)
        self.assertIn("cannot check that %s is private" % url, out)
        self.assertFalse((self.repo / ".lattice").exists(), out)

    def test_git_settings_that_send_pushes_elsewhere_are_refused_before_anything_is_made(self):
        private, public = self.serve(password="pw"), self.serve()
        base = (self.home / ".gitconfig").read_text() + CREDENTIALS
        for rule in ('[url "https://127.0.0.1:9/board.git"]\n\tinsteadOf = %s\n' % private,
                     '[url "%s"]\n\tpushInsteadOf = %s\n' % (public, private)):
            (self.home / ".gitconfig").write_text(base + rule)
            code, out = self.run_script("--remote", private)
            self.assertEqual(code, 1, out)
            self.assertIn("your Git settings send pushes for %s" % private, out)
            self.assertIn("nothing was changed", out)
            self.assertFalse((self.repo / ".lattice").exists(), out)
        self.assertEqual(self.git("for-each-ref", cwd=self.remote), "")

    def test_settings_only_the_board_repository_sees_stop_the_push(self):
        private, public = self.serve(password="pw"), self.serve()
        only = pathlib.Path(self.tmp.name, "board-only.gitconfig")
        only.write_text('[url "%s"]\n\tpushInsteadOf = %s\n' % (public, private))
        with open(self.home / ".gitconfig", "a") as config:
            config.write(CREDENTIALS + '[includeIf "gitdir:%s/.lattice/"]\n\tpath = %s\n' % (self.repo, only))
        code, out = self.run_script("--remote", private)
        self.assertEqual(code, 1, out)
        self.assertIn("your Git settings send pushes for %s" % private, out)
        self.assertIn("nothing was pushed", out)
        self.assertEqual(self.git("for-each-ref", cwd=self.remote), "")

    def test_a_project_on_another_branch_gets_it_as_the_review_base(self):
        self.git("checkout", "-q", "-b", "staging")
        self.git("config", "lattice-review.base", "other")
        code, out = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("lattice-review.base is other", out)
        self.assertFalse((self.repo / ".lattice").exists(), out)
        self.git("config", "--unset", "lattice-review.base")
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("config", "--get", "lattice-review.base"), "staging")
        self.assertIn("The integration branch is staging.", (self.repo / ".lattice/context.md").read_text())

    def test_what_it_cannot_do_safely_is_refused_before_anything_is_made(self):
        (self.repo / "sub").mkdir()
        for args, cwd, said in ((("--actor", "agent:x"), None, "is a person"),
                                (("--remote", str(self.remote) + "-missing"), None, "cannot reach"),
                                (("--remote", "https://u:token@example.invalid/board.git"), None, "user or token"),
                                (("--remote", "git@github.com:o/r.git"), None, "give the board's https address"),
                                (("--remote", str(self.remote)), None, "pushed only to the https address"),
                                (("--remote", "http://example.invalid/board.git"), None, "give the board's https address"),
                                (("--port", "1"), None, "unknown argument"),
                                ((), self.repo / "sub", "from the top of the repository")):
            code, out = self.run_script(*args, cwd=cwd)
            self.assertEqual(code, 1, out)
            self.assertIn(said, out)
            self.assertFalse((self.repo / ".lattice").exists(), out)


if __name__ == "__main__":
    unittest.main()
