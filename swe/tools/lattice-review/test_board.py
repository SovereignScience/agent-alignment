"""board.bash, with a stand-in review server, against ports held by other programs."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUB = "import json, os, sys\nopen(os.environ['BOARD_TEST_LOG'], 'w').write(json.dumps(sys.argv[1:]))\n"
HOLD = ("import socket, time\n"
        "s = socket.socket()\ns.bind(('127.0.0.1', 0))\ns.listen()\n"
        "print(s.getsockname()[1], flush=True)\ntime.sleep(120)\n")


class Board(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        kit = self.tmp / "kit"
        (kit / "swe/tools/lattice-review").mkdir(parents=True)
        (kit / "swe/tools/lattice-review/lattice_review.py").write_text(STUB)
        self.function = self.tmp / "board.bash"
        self.function.write_text((HERE / "board.bash").read_text().replace("@KIT@", str(kit)))
        self.root = self.tmp / "project"
        (self.root / ".lattice").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.log = self.tmp / "started.json"

    def hold(self, *args, cwd=None, script="lattice_review.py", options=()):
        """The port of a stand-in listener started as `python <options> <script> args`."""
        path = self.tmp / "listeners" / script
        path.parent.mkdir(exist_ok=True)
        path.write_text(HOLD)
        proc = subprocess.Popen([sys.executable, *options, str(path), *args], cwd=cwd, stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.addCleanup(proc.stdout.close)
        return int(proc.stdout.readline())

    def give_port(self, port):
        (self.root / ".lattice/config.json").write_text(json.dumps({"dashboard_port": port, "default_actor": "human:t"}))
        (self.root / ".lattice/context.md").write_text("- Review flow: the owner opens the board at http://127.0.0.1:%d\n" % port)

    def board(self, status=0):
        env = dict(os.environ, BOARD_TEST_LOG=str(self.log))
        self.log.unlink(missing_ok=True)
        run = subprocess.run(["bash", "-c", 'source "$1" && board', "bash", str(self.function)],
                             cwd=self.root, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, status, run.stderr)
        started = json.loads(self.log.read_text()) if self.log.exists() else None
        return run.stdout + run.stderr, started

    def test_a_port_another_board_holds_moves_this_board_to_a_free_one(self):
        taken = self.hold("--board", str(self.tmp / "other"))
        self.give_port(taken)
        out, started = self.board()
        self.assertIsNotNone(started, out)
        new = int(started[started.index("--port") + 1])
        self.assertNotEqual(new, taken)
        self.assertTrue(8803 <= new <= 8899, new)
        self.assertEqual(started[started.index("--board") + 1], str(self.root))
        self.assertEqual(json.loads((self.root / ".lattice/config.json").read_text())["dashboard_port"], new)
        self.assertIn("127.0.0.1:%d\n" % new, (self.root / ".lattice/context.md").read_text())
        self.assertIn("now uses port %d" % new, out)

    def test_a_move_never_reads_or_writes_through_a_link_in_the_board(self):
        taken = self.hold("--board", str(self.tmp / "other"))
        outside = self.tmp / "owner"
        outside.mkdir()
        for name in ("config.json", "context.md", "config.json.new", "context.md.new"):
            (outside / name).write_text("the owner's %s 127.0.0.1:%d\n" % (name, taken))
        lattice = self.root / ".lattice"
        for planted in ("context.md", ".lattice"):
            with self.subTest(planted):
                if lattice.is_symlink():
                    lattice.unlink()
                else:
                    shutil.rmtree(lattice)
                lattice.mkdir()
                self.give_port(taken)
                for name in ("config.json.new", "context.md.new"):
                    (lattice / name).symlink_to(outside / name)
                if planted == ".lattice":
                    shutil.copy(lattice / "config.json", outside / "config.json")
                    shutil.rmtree(lattice)
                    lattice.symlink_to(outside)
                else:
                    (lattice / planted).unlink()
                    (lattice / planted).symlink_to(outside / planted)
                out, started = self.board(status=1)
                self.assertIsNone(started)
                self.assertIn("the board in %s holds a link (%s); nothing was changed" % (self.root, planted), out)
                for name in ("context.md", "config.json.new", "context.md.new"):
                    self.assertEqual((outside / name).read_text(), "the owner's %s 127.0.0.1:%d\n" % (name, taken))

    def test_this_boards_own_server_is_left_running(self):
        for how, port in (("board", self.hold("--board", str(self.root))),
                          ("the long way", self.hold("--actor", "human:t", cwd=self.root)),
                          ("with an attached -W value", self.hold("--board", str(self.root), options=("-Wignore",)))):
            with self.subTest(how):
                self.give_port(port)
                out, started = self.board()
                self.assertIsNone(started)
                self.assertIn("already running on port %d" % port, out)
                self.assertEqual(json.loads((self.root / ".lattice/config.json").read_text())["dashboard_port"], port)

    def test_a_listener_that_only_names_the_server_is_not_this_boards(self):
        board = ("--board", str(self.root))
        listeners = self.tmp / "listeners"
        listeners.mkdir()
        (listeners / "listener.py").write_text(HOLD)
        for how, script, args, options in (
                ("another script", "unrelated_lattice_review.py", board, ()),
                ("a plain argument", "listener.py", ("lattice_review.py",) + board, ()),
                ("-c<code>", "lattice_review.py", board, ("-c" + HOLD,)),
                ("-Bc<code>", "lattice_review.py", board, ("-Bc" + HOLD,)),
                ("-mlistener", "lattice_review.py", board, ("-mlistener",)),
                ("-Bmlistener", "lattice_review.py", board, ("-Bmlistener",))):
            with self.subTest(how):
                port = self.hold(*args, script=script, options=options, cwd=listeners)
                self.give_port(port)
                out, started = self.board()
                self.assertIsNotNone(started, out)
                self.assertNotEqual(int(started[started.index("--port") + 1]), port)


if __name__ == "__main__":
    unittest.main()
