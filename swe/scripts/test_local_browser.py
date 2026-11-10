"""local_browser.py against a real headless shell and a throwaway local site.

The browser tests skip where no headless shell is installed. Set
SWE_HEADLESS_SHELL to a headless shell build to run them elsewhere.
"""
import json
import os
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

SCRIPT = pathlib.Path(__file__).resolve().parent / "local_browser.py"
sys.path.insert(0, str(SCRIPT.parent))
import local_browser  # noqa: E402

SHELL = os.environ.get("SWE_HEADLESS_SHELL") or shutil.which("chromium-headless-shell")

INDEX = """<!doctype html><title>probe</title>
<body style="margin:0">
<h1 style="color:#eee">light text, no background</h1>
<input id="name"><button id="ask">ask</button><p id="said"></p>
<img src="http://example.com/outside.png" alt="">
<div style="height:3000px"></div><p id="end">end</p>
<script>
document.getElementById('ask').onclick = () => {
  const ok = confirm('really?');
  document.getElementById('said').textContent = (ok ? 'yes ' : 'no ') + document.getElementById('name').value;
};
navigator.serviceWorker.register('/sw.js').catch(e => console.log('sw refused'));
</script>
"""


def pixel(path, x, y):
    """One pixel of an 8-bit RGB or RGBA PNG, read with the standard library."""
    raw = pathlib.Path(path).read_bytes()
    width, _, _, colour_type = struct.unpack(">IIBB", raw[16:26])
    step = {2: 3, 6: 4}[colour_type]
    position, packed = 8, b""
    while position < len(raw):
        length, kind = struct.unpack(">I4s", raw[position:position + 8])
        if kind == b"IDAT":
            packed += raw[position + 8:position + 8 + length]
        position += 12 + length
    data, stride = zlib.decompress(packed), width * step
    before = bytearray(stride)
    for row in range(y + 1):
        kind = data[row * (stride + 1)]
        line = bytearray(data[row * (stride + 1) + 1:(row + 1) * (stride + 1)])
        for i in range(stride):
            left = line[i - step] if i >= step else 0
            up = before[i]
            corner = before[i - step] if i >= step else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                guess = left + up - corner
                near = min((abs(guess - left), 0, left), (abs(guess - up), 1, up), (abs(guess - corner), 2, corner))
                line[i] = (line[i] + near[2]) & 255
        before = line
    return tuple(before[x * step:x * step + 3])


def height(path):
    return struct.unpack(">I", pathlib.Path(path).read_bytes()[20:24])[0]


class Addresses(unittest.TestCase):
    def test_only_loopback_counts_as_local(self):
        for url in ("http://localhost:8000/", "http://127.0.0.1/x", "https://127.8.9.1:1/", "http://[::1]:3000/",
                    "ws://app.localhost/socket", "http://LOCALHOST./"):
            with self.subTest(url=url):
                self.assertTrue(local_browser.is_local(url))
        for url in ("http://example.com/", "http://localhost.example.com/", "http://169.254.169.254/latest",
                    "http://192.168.1.10/", "http://0.0.0.0/", "file:///etc/passwd", "http://127.0.0.1.example.com/",
                    "http://user@example.com@127.0.0.1.evil.test/", "javascript:alert(1)", "http:///nohost"):
            with self.subTest(url=url):
                self.assertFalse(local_browser.is_local(url))


class Refusals(unittest.TestCase):
    def run_script(self, *args, env=None):
        run = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, **(env or {})))
        return run.returncode, run.stdout + run.stderr

    def test_a_remote_address_is_refused_before_anything_starts(self):
        code, out = self.run_script("https://example.com/")
        self.assertEqual(code, 2)
        self.assertIn("not a local address", out)

    def test_a_missing_browser_says_to_ask_the_owner_and_uses_no_other(self):
        code, out = self.run_script("http://127.0.0.1:9/",
                                    env={"SWE_HEADLESS_SHELL": "/nonexistent/chromium-headless-shell"})
        self.assertEqual(code, 3)
        self.assertIn("Ask the owner to install it", out)

    def test_a_shortened_option_is_refused_so_the_guard_always_sees_the_app_command(self):
        code, out = self.run_script("--ap", "true", "http://127.0.0.1:9/")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", out)

    def test_another_browser_is_not_accepted(self):
        code, out = self.run_script("http://127.0.0.1:9/", env={"SWE_HEADLESS_SHELL": sys.executable})
        self.assertEqual(code, 3)
        self.assertIn("not a headless shell build", out)


@unittest.skipUnless(SHELL, "no headless shell installed; set SWE_HEADLESS_SHELL")
class LocalSite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.site = pathlib.Path(self.tmp.name, "site")
        self.site.mkdir()
        (self.site / "index.html").write_text(INDEX)
        self.out = pathlib.Path(self.tmp.name, "shots")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.url = "http://127.0.0.1:%d/" % self.port
        self.app = "%s -m http.server %d --bind 127.0.0.1 --directory %s" % (sys.executable, self.port, self.site)

    def browse(self, *args, app=True):
        command = [sys.executable, str(SCRIPT), "--out", str(self.out), "--timeout", "15"]
        if app:
            command += ["--app", self.app]
        run = subprocess.run(command + list(args), capture_output=True, text=True, timeout=120,
                             env=dict(os.environ, SWE_HEADLESS_SHELL=SHELL))
        return run.returncode, json.loads(run.stdout), run.stderr

    def port_is_closed(self):
        with socket.socket() as probe:
            return probe.connect_ex(("127.0.0.1", self.port)) != 0

    def test_a_shot_covers_the_whole_page_on_the_chosen_background(self):
        code, report, err = self.browse("--background", "#202124", self.url, "wait:#end", "shot:dark")
        self.assertEqual((code, err), (0, ""), report)
        shot = report["screenshots"][0]
        self.assertEqual(shot, str(self.out / "dark.png"))
        self.assertGreater(height(shot), 3000)
        self.assertEqual(pixel(shot, 700, 2000), (0x20, 0x21, 0x24))
        self.assertTrue(self.port_is_closed(), "the app was left running")

    def test_with_no_step_one_shot_is_taken_on_white(self):
        code, report, _ = self.browse(self.url)
        self.assertEqual(code, 0, report)
        self.assertEqual(pixel(report["screenshots"][0], 700, 2000), (255, 255, 255))

    def test_typing_a_click_and_an_accepted_dialog_reach_the_page(self):
        code, report, _ = self.browse(self.url, "click:#name", "text:Ada", "dialog:accept", "click:#ask",
                                      "eval:document.getElementById('said').textContent", "shot:after")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["results"][0]["value"], "yes Ada")
        self.assertEqual(report["dialogs"], [{"type": "confirm", "message": "really?", "answer": "accepted"}])

    def test_a_dialog_is_dismissed_unless_told_otherwise(self):
        code, report, _ = self.browse(self.url, "click:#ask", "eval:document.getElementById('said').textContent")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["results"][0]["value"], "no ")

    def test_requests_off_this_machine_are_blocked_and_service_workers_refused(self):
        code, report, _ = self.browse(self.url, "wait:#end",
                                      "eval:fetch('http://example.com/x').then(() => 'sent', () => 'blocked')")
        self.assertEqual(code, 0, report)
        self.assertIn("http://example.com/outside.png", report["blocked"])
        self.assertEqual(report["results"][0]["value"], "blocked")
        self.assertIn("log: sw refused", report["console"])

    def test_a_missing_element_fails_the_step_and_names_it(self):
        code, report, _ = self.browse("--timeout", "2", self.url, "click:#nothing-here")
        self.assertEqual(code, 1)
        self.assertEqual(report["step"], "click:#nothing-here")
        self.assertIn("waiting for an element matching #nothing-here", report["problem"])
        self.assertTrue(self.port_is_closed(), "the app was left running")

    def test_an_app_that_never_answers_is_reported_with_its_output(self):
        self.app = "echo starting up; sleep 30"
        code, report, _ = self.browse("--timeout", "2", self.url)
        self.assertEqual(code, 4)
        self.assertIn("did not answer", report["problem"])
        self.assertIn("starting up", report["problem"])

    def test_without_an_app_the_report_says_why_nothing_answered(self):
        code, report, _ = self.browse(self.url, app=False)
        self.assertEqual(code, 1)
        self.assertIn("start the app here with --app", report["problem"])

    def test_a_step_cannot_leave_this_machine(self):
        code, report, _ = self.browse(self.url, "goto:https://example.com/")
        self.assertEqual(code, 2)
        self.assertIn("not a local address", report["problem"])


if __name__ == "__main__":
    unittest.main()
