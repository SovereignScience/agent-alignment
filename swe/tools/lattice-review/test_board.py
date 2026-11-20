"""board.bash, with a stand-in review server, against ports held by other programs."""
import json
import os
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

    def hold(self, *args):
        """The port of a process listening on a free one, with args on its command line."""
        proc = subprocess.Popen([sys.executable, "-c", HOLD, *args], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.addCleanup(proc.stdout.close)
        return int(proc.stdout.readline())

    def give_port(self, port):
        (self.root / ".lattice/config.json").write_text(json.dumps({"dashboard_port": port, "default_actor": "human:t"}))
        (self.root / ".lattice/context.md").write_text("- Review flow: the owner opens the board at http://127.0.0.1:%d\n" % port)

    def board(self):
        env = dict(os.environ, BOARD_TEST_LOG=str(self.log))
        run = subprocess.run(["bash", "-c", 'source "$1" && board', "bash", str(self.function)],
                             cwd=self.root, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        started = json.loads(self.log.read_text()) if self.log.exists() else None
        return run.stdout, started

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

    def test_this_boards_own_server_is_left_running(self):
        port = self.hold("--board", str(self.root))
        self.give_port(port)
        out, started = self.board()
        self.assertIsNone(started)
        self.assertIn("already running on port %d" % port, out)
        self.assertEqual(json.loads((self.root / ".lattice/config.json").read_text())["dashboard_port"], port)


if __name__ == "__main__":
    unittest.main()
