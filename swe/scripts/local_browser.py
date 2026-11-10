#!/usr/bin/env python3
"""Open a local page in the headless browser, act on it and take screenshots.

    local_browser.py [--app CMD] [--out DIR] [--size WxH] [--background '#rrggbb']
                     [--scheme light|dark] [--timeout SECONDS] URL [STEP ...]

Steps run in order once URL has loaded. With no step it takes one shot.

    shot:NAME          full-page screenshot, saved as DIR/NAME.png
    wait:SELECTOR      wait until an element matches the CSS selector
    click:SELECTOR     scroll the element into view and click its centre
    text:STRING        type into the element that has focus
    dialog:accept      answer alert, confirm and prompt dialogs from here on;
    dialog:dismiss     dialog:accept=TEXT also fills in a prompt (default: dismiss)
    eval:JAVASCRIPT    evaluate an expression and put its value in the report
    goto:URL           load another local page

In a sandboxed session a command's localhost is its own, so a server started
elsewhere is out of reach: pass --app and the app starts here, is waited for
until URL answers, and is stopped at the end. Example:

    local_browser.py --app 'python3 -m http.server 8123 --bind 127.0.0.1' \\
        http://127.0.0.1:8123/ wait:h1 shot:before click:#save shot:after

A JSON report goes to stdout: screenshots, eval results, dialogs, console
messages, page errors and requests that failed or were blocked. Exit status:
0 done, 1 a step failed, 2 bad arguments, 3 no browser, 4 the app did not start.

Only chromium-headless-shell is used (SWE_HEADLESS_SHELL names another build
of it). Only localhost, 127.0.0.0/8 and [::1] are opened; every other request
is failed. Each run gets a fresh profile, and service workers are refused.
These are security rule 12's limits. The sandbox stays the boundary.
"""
import argparse
import base64
import fcntl
import ipaddress
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_SHOT_HEIGHT = 16384  # Chromium's largest screenshot side.
FIXED_FLAGS = (
    "--no-sandbox",  # Chromium's own sandbox cannot start inside the agent sandbox.
    "--remote-debugging-pipe",  # No debugging port for another process to attach to.
    "--proxy-server=http://127.0.0.1:9",  # A closed port. Loopback bypasses it; other hosts fail.
    # No name lookups except for this machine. IP literals pass through this rule too.
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE *.localhost, EXCLUDE 127.*, EXCLUDE [::1]",
    "--disable-background-networking",
    "--disable-component-update",
    "--hide-scrollbars",
)
NO_SERVICE_WORKERS = (
    "if (navigator.serviceWorker) navigator.serviceWorker.register = "
    "() => Promise.reject(new Error('service workers are refused in this browser'));"
)
LOCATE = """(() => { const e = document.querySelector(%s); if (!e) return null;
  e.scrollIntoView({block: 'center', inline: 'center'});
  const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()"""
NOT_LOCAL = "%s is not a local address; this browser opens only localhost, 127.0.0.0/8 and [::1]."
SETTLED = "document.fonts.ready.then(() => new Promise(done => requestAnimationFrame(() => done(true))))"


class Problem(Exception):
    """A failure to report in plain words; its code is the exit status."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def is_local(url):
    """True for an http(s) or ws(s) address on this machine's loopback."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").rstrip(".").lower()
    if parts.scheme not in ("http", "https", "ws", "wss") or not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def find_browser():
    path = os.environ.get("SWE_HEADLESS_SHELL") or shutil.which("chromium-headless-shell")
    if not path or not os.access(path, os.X_OK):
        raise Problem("chromium-headless-shell is not installed. Ask the owner to install it "
                      "(sudo apt install chromium-headless-shell). No other browser is used.", 3)
    if not re.search(r"headless[-_]shell", os.path.basename(path)):
        raise Problem("%s is not a headless shell build; no other browser is used." % path, 3)
    return path


def colour(text):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        raise argparse.ArgumentTypeError("give the colour as #rrggbb")
    return {"r": int(text[1:3], 16), "g": int(text[3:5], 16), "b": int(text[5:7], 16), "a": 1}


def size(text):
    if not re.fullmatch(r"[1-9]\d{1,3}x[1-9]\d{1,3}", text):
        raise argparse.ArgumentTypeError("give the size as WIDTHxHEIGHT, such as 1280x800")
    return tuple(int(n) for n in text.split("x"))


class App:
    """The app under test, started here because a sandboxed localhost is private."""

    def __init__(self, command, url, timeout, workdir):
        self.log = os.path.join(workdir, "app.log")
        with open(self.log, "w") as log:
            self.process = subprocess.Popen(command, shell=True, start_new_session=True,
                                            stdout=log, stderr=subprocess.STDOUT)
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + timeout
        while True:
            try:
                direct.open(url, timeout=2).close()
                return
            except urllib.error.HTTPError:
                return  # Any HTTP answer means the app is up.
            except OSError:
                pass
            if self.process.poll() is not None:
                self.fail("The app exited before %s answered." % url)
            if time.monotonic() > deadline:
                self.fail("The app did not answer at %s within %d seconds." % (url, timeout))
            time.sleep(0.2)

    def fail(self, message):
        self.stop()
        with open(self.log, errors="replace") as log:
            tail = "".join(log.readlines()[-15:]).rstrip()
        raise Problem("%s Its last output:\n%s" % (message, tail or "(none)"), 4)

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()


class Browser:
    """One headless shell and one page, driven over the DevTools pipe."""

    def __init__(self, binary, profile, timeout):
        self.timeout = timeout
        self.buffer = b""
        self.last_id = 0
        self.session = None
        self.answer = {"accept": False}
        self.loaded = False
        self.urls = {}
        self.report = {"screenshots": [], "results": [], "dialogs": [], "console": [],
                       "errors": [], "blocked": [], "failed": [], "notes": []}
        to_browser, self.send_fd = os.pipe()
        self.read_fd, from_browser = os.pipe()
        # The browser reads commands on descriptor 3 and writes on 4. Move our
        # ends clear of those numbers first so the two dup2 calls cannot collide.
        high = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (to_browser, from_browser)]
        os.makedirs(profile)
        self.log = os.path.join(profile, "browser.log")
        self.pid = os.posix_spawn(binary, [binary, *FIXED_FLAGS, "--user-data-dir=" + profile, "about:blank"],
                                  os.environ, setpgroup=0, file_actions=[
            (os.POSIX_SPAWN_DUP2, high[0], 3), (os.POSIX_SPAWN_DUP2, high[1], 4),
            (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
            (os.POSIX_SPAWN_OPEN, 2, self.log, os.O_WRONLY | os.O_CREAT, 0o600)])
        for fd in (to_browser, from_browser, *high):
            os.close(fd)

    def close(self):
        try:
            os.killpg(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(self.send_fd)
        os.close(self.read_fd)

    def send(self, method, params=None, session=True):
        self.last_id += 1
        message = {"id": self.last_id, "method": method, "params": params or {}}
        if session and self.session:
            message["sessionId"] = self.session
        os.write(self.send_fd, json.dumps(message).encode() + b"\0")
        return self.last_id

    def receive(self, deadline):
        while b"\0" not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.read_fd], [], [], left)[0]:
                raise Problem("The browser did not answer within %d seconds." % self.timeout)
            chunk = os.read(self.read_fd, 1 << 16)
            if not chunk:
                with open(self.log, errors="replace") as log:
                    raise Problem("The browser stopped. Its last output:\n" + log.read()[-800:].strip())
            self.buffer += chunk
        message, _, self.buffer = self.buffer.partition(b"\0")
        return json.loads(message)

    def call(self, method, params=None, session=True):
        """Send one command and return its result, handling events that arrive first."""
        wanted = self.send(method, params, session)
        deadline = time.monotonic() + self.timeout
        while True:
            message = self.receive(deadline)
            if message.get("id") == wanted:
                if "error" in message:
                    raise Problem("%s failed: %s" % (method, message["error"].get("message")))
                return message["result"]
            if "method" in message:
                self.on_event(message["method"], message.get("params", {}))

    def on_event(self, method, params):
        report = self.report
        if method == "Fetch.requestPaused":
            url = params["request"]["url"]
            if is_local(url):
                self.send("Fetch.continueRequest", {"requestId": params["requestId"]})
            else:
                report["blocked"].append(url)
                self.send("Fetch.failRequest", {"requestId": params["requestId"], "errorReason": "BlockedByClient"})
        elif method == "Page.javascriptDialogOpening":
            report["dialogs"].append({"type": params["type"], "message": params["message"],
                                      "answer": "accepted" if self.answer["accept"] else "dismissed"})
            self.send("Page.handleJavaScriptDialog", self.answer)
        elif method == "Page.loadEventFired":
            self.loaded = True
        elif method == "Runtime.consoleAPICalled":
            text = " ".join(str(a.get("value", a.get("description", ""))) for a in params["args"])
            report["console"].append("%s: %s" % (params["type"], text))
        elif method == "Runtime.exceptionThrown":
            detail = params["exceptionDetails"]
            report["errors"].append(detail.get("exception", {}).get("description") or detail.get("text"))
        elif method == "Network.requestWillBeSent":
            self.urls[params["requestId"]] = params["request"]["url"]
        elif method == "Network.loadingFailed" and "BLOCKED_BY_CLIENT" not in params.get("errorText", ""):
            report["failed"].append("%s: %s" % (self.urls.get(params["requestId"], "?"), params.get("errorText")))

    def start_page(self, viewport, background, scheme):
        pages = [t for t in self.call("Target.getTargets")["targetInfos"] if t["type"] == "page"]
        target = pages[0]["targetId"] if pages else self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.session = self.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        for domain in ("Page", "Runtime", "Network"):
            self.call(domain + ".enable")
        self.call("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        self.call("Network.setBypassServiceWorker", {"bypass": True})
        self.call("Page.addScriptToEvaluateOnNewDocument", {"source": NO_SERVICE_WORKERS})
        self.call("Emulation.setDeviceMetricsOverride",
                  {"width": viewport[0], "height": viewport[1], "deviceScaleFactor": 1, "mobile": False})
        self.call("Emulation.setDefaultBackgroundColorOverride", {"color": background})
        self.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": scheme}]})

    def until(self, condition, what):
        """Poll an observable condition up to the timeout; never a fixed sleep."""
        deadline = time.monotonic() + self.timeout
        while True:
            value = condition()
            if value:
                return value
            if time.monotonic() > deadline:
                raise Problem("Timed out after %d seconds waiting for %s." % (self.timeout, what))
            time.sleep(0.1)

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            raise Problem("The page raised: %s" % (detail.get("exception", {}).get("description") or detail["text"]))
        return result["result"].get("value")

    def goto(self, url):
        if not is_local(url):
            raise Problem(NOT_LOCAL % url, 2)
        self.loaded = False
        error = self.call("Page.navigate", {"url": url}).get("errorText")
        if error:
            raise Problem("Nothing answered at %s (%s). In a sandboxed session a server started by another "
                          "command or on the host is out of reach; start the app here with --app." % (url, error))
        try:
            self.until(lambda: self.evaluate("document.readyState") == "complete" or self.loaded, "the page to load")
        except Problem:
            self.report["notes"].append("%s did not finish loading within %d seconds; went on." % (url, self.timeout))

    def click(self, selector):
        x, y = self.until(lambda: self.evaluate(LOCATE % json.dumps(selector)), "an element matching %s" % selector)
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})

    def shot(self, path):
        self.evaluate(SETTLED)
        content = self.call("Page.getLayoutMetrics")["cssContentSize"]
        height = content["height"]
        if height > MAX_SHOT_HEIGHT:
            self.report["notes"].append("%s is cut at %d of %d pixels."
                                        % (os.path.basename(path), MAX_SHOT_HEIGHT, height))
            height = MAX_SHOT_HEIGHT
        data = self.call("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": True,
            "clip": {"x": 0, "y": 0, "width": content["width"], "height": height, "scale": 1}})["data"]
        with open(path, "wb") as image:
            image.write(base64.b64decode(data))
        self.report["screenshots"].append(path)

    def run(self, step, out):
        verb, _, value = step.partition(":")
        if verb == "shot" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
            self.shot(os.path.join(out, value + ".png"))
        elif verb == "wait" and value:
            self.until(lambda: self.evaluate("!!document.querySelector(%s)" % json.dumps(value)),
                       "an element matching %s" % value)
        elif verb == "click" and value:
            self.click(value)
        elif verb == "text":
            self.call("Input.insertText", {"text": value})
        elif verb == "dialog" and value.split("=", 1)[0] in ("accept", "dismiss"):
            self.answer = {"accept": value.startswith("accept")}
            if "=" in value:
                self.answer["promptText"] = value.split("=", 1)[1]
        elif verb == "eval" and value:
            self.report["results"].append({"eval": value, "value": self.evaluate(value)})
        elif verb == "goto":
            self.goto(value)
        else:
            raise Problem("Unknown step %r. Steps: shot:NAME wait:SELECTOR click:SELECTOR text:STRING "
                          "dialog:accept|dismiss eval:JAVASCRIPT goto:URL." % step, 2)


def main(argv=None):
    # No abbreviated options: the guard hook reads --app by its full name.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("--app", metavar="CMD", help="command that starts the app; stopped at the end")
    parser.add_argument("--out", metavar="DIR", help="folder for screenshots (default: a new folder under $TMPDIR)")
    parser.add_argument("--size", type=size, default=(1280, 800), metavar="WxH", help="viewport (default 1280x800)")
    parser.add_argument("--background", type=colour, default=colour("#ffffff"), metavar="'#rrggbb'",
                        help="colour behind a page that sets none (default white)")
    parser.add_argument("--scheme", choices=("light", "dark"), default="light", help="preferred colour scheme")
    parser.add_argument("--timeout", type=int, default=20, metavar="SECONDS",
                        help="limit for each wait, and for the app to answer (default 20)")
    parser.add_argument("url", metavar="URL")
    parser.add_argument("steps", nargs="*", metavar="STEP")
    args = parser.parse_args(argv)
    steps = args.steps or ["shot:page"]
    app = browser = None
    code = 0
    report = {}
    with tempfile.TemporaryDirectory(prefix="local-browser-") as workdir:
        try:
            if not is_local(args.url):
                raise Problem(NOT_LOCAL % args.url, 2)
            binary = find_browser()
            out = args.out or tempfile.mkdtemp(prefix="shots-")
            os.makedirs(out, exist_ok=True)
            if args.app:
                app = App(args.app, args.url, args.timeout, workdir)
            browser = Browser(binary, os.path.join(workdir, "profile"), args.timeout)
            report = browser.report
            browser.start_page(args.size, args.background, args.scheme)
            browser.goto(args.url)
            for step in steps:
                report["step"] = step
                browser.run(step, os.path.abspath(out))
            del report["step"]
        except Problem as problem:
            code = problem.code
            report["problem"] = str(problem)
        finally:
            if browser:
                browser.close()
            if app:
                app.stop()
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
