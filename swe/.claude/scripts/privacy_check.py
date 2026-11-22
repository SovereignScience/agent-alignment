#!/usr/bin/python3 -I
"""privacy_check: stop a commit or push that would publish a private detail.

It runs only in a repository with a .privacy-allow file at its top, which marks
the repository as public. A commit or push that removes that file is refused,
so only --no-verify turns the check off. The hooks call it three ways:
  privacy_check.py staged          pre-commit: the staged change
  privacy_check.py message <file>  commit-msg: the commit message
  check_push()                     pre-push: each commit being pushed, so a
                                   detail a later commit removed is still found
It reads added lines, new and renamed paths, base64 and percent-encoded text,
PNG and JPEG metadata and commit messages. It looks for home paths, email
addresses, internal hostnames, IP addresses, human:<name> actor labels, UUIDs,
AWS account IDs, named fields such as author or owner, and credentials. It also
looks for names it reads from this machine as it runs, so none is stored in a
repository: the committer's Git name and email, the login and hostname, the
folders beside the repository's main checkout (names only, and only those the
tracked files do not already hold), and the names in
~/.config/agent-alignment/privacy-names when that file exists. Every binary
file, images included, is reported by its blob id until someone has looked at
it, since pixels can show what metadata does not.
Each finding is printed with a placeholder to use instead. It changes nothing
and exits 1, so Git cancels. A value that is public anyway, and is not a
credential, goes on its own line in .privacy-allow; a line there with a
credential shape is refused.
"""
import base64
import binascii
import codecs
import getpass
import ipaddress
import os
import re
import socket
import subprocess
import sys
import urllib.parse
import zlib
from collections import namedtuple

ALLOW = ".privacy-allow"
REMOVED = "this removes %s, which would turn the privacy check off; to do that on purpose, use --no-verify" % ALLOW
Finding = namedtuple("Finding", "where kind value")
SUGGEST = {
    "home path": "use ~/, $HOME/ or /home/<user>/",
    "email": "use <email> or user@example.com",
    "internal host": "use <host> or host.example",
    "IP address": "use <ip> or 192.0.2.10",
    "actor label": "use human:<name> or human:owner",
    "identifier": "use <id>",
    "named field": "use <name> or <project>",
    "name": "use <name>, <project> or a role such as the owner",
    "credential": "remove it, and rotate it if it was ever real",
    "binary": "open it and check it; if it holds nothing private, add this blob id to " + ALLOW,
}
GENERIC = frozenset((
    "user", "username", "me", "you", "name", "someone", "owner", "nobody", "root", "runner", "admin",
    "test", "ubuntu", "vscode", "node", "app", "dev", "localhost"))
GENERIC_FOLDERS = frozenset((
    "backup", "backups", "archive", "archives", "scratch", "temp", "tests", "old", "new", "notes", "docs",
    "work", "projects", "misc", "downloads", "sandbox", "playground", "examples"))
DOC_NETS = tuple(ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))

HOME_PATH = re.compile(r"(?:(?<![\w.~-])/(?:home|Users)|/mnt/[a-z]/Users|(?<!\w)[A-Za-z]:(?:\\{1,2}|/)Users)"
                       r"(?:\\{1,2}|/)([^\s/\\'\"`<>:;,()\[\]{}|*?]+)")
EMAIL = re.compile(r"(?<![\w.+-])([\w.+-]+)@((?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,24})(?![\w-])")
INTERNAL = re.compile(r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(lan|internal|intranet|corp|home\.arpa|"
                      r"ts\.net|local))(?![\w-]|\.[a-z0-9])", re.I)
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?!\d|\.\d)")
ACTOR = re.compile(r"(?<![\w-])human:([A-Za-z0-9][\w.-]*)")
UUID = re.compile(r"(?<![\w-])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![\w-])")
ARN = re.compile(r"\barn:aws[\w-]*:[\w-]*:[\w-]*:(\d{12})(?=:)")
FIELD = re.compile(r"""(?i)(?:^|[\s{,(])["']?(author|maintainer|owner|username|login|account|email|hostname|"""
                   r"""organi[sz]ation|org|tenant|customer|company)["']?\s*[:=]\s*["']([^"'\n]{2,60})["']""")
NAME_LIKE = re.compile(r"[A-Za-z][\w.+@-]*(?: [A-Za-z][\w.+-]*){0,3}")
CREDENTIAL = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?<![\w-])(?:gh[pousr]_[A-Za-z0-9]{36,}|"
                        r"github_pat_\w{60,}|(?:AKIA|ASIA)[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|"
                        r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|eyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,})|"
                        r"://[^\s/:@]+:([^\s/@]+)@([^\s/:'\"]+)")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]+")
SECRET_FIELD = re.compile(r"""(?i)(?<![\w-])["']?(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"""
                          r"""private[_-]?key)["']?\s*[:=]\s*["']([^"'\s]{8,})["']""")
COPYRIGHT = re.compile(r"(?i)^\W*(?:copyright\b|\(c\)\s*\d{4}|©)")
TRAILER = re.compile(r"^[\w-]+-by:\s")
SCISSORS = re.compile(r"^\S ------------------------ >8 ------------------------$")
B64 = re.compile(r"[A-Za-z0-9+/_-]{24,}={0,2}")


class GitError(Exception):
    pass


class AllowError(Exception):
    pass


def git(*args, binary=False, stdin=None):
    out = subprocess.run(["git", "-c", "core.quotepath=off", *args], input=stdin, capture_output=True)
    if out.returncode != 0:
        raise GitError("git %s: %s" % (" ".join(args[:2]), out.stderr.decode(errors="replace").strip()[:200]))
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def placeholder(value):
    v = value.strip().strip("'\"`").lower()
    return (not v or v[0] in "<$%{[*" or v in GENERIC or "example" in v or "xxx" in v or "your" in v
            or v.startswith(("changeme", "dummy", "fake", "redacted")))


def reserved(host):
    h = host.lower().rstrip(".")
    return h in ("localhost", "example.com", "example.net", "example.org") or h.endswith(
        (".example.com", ".example.net", ".example.org", ".example", ".test", ".invalid", ".localhost"))


def flagged_ip(text):
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return not (any(ip in net for net in DOC_NETS) or ip.is_loopback or ip.is_unspecified or ip.is_link_local
                or ip.is_multicast or ip.is_reserved)


def meaningful(name):
    return len(name) >= 3 and bool(re.search("[A-Za-z]", name)) and not placeholder(name)


def shapes(text):
    """(kind, value, name it reveals or None) for each shape in one line. Credentials come first, and their
    whole span is blanked before the other shapes are looked for, so no other finding holds part of one."""
    for pattern in (CREDENTIAL, SECRET_FIELD):
        for m in pattern.finditer(text):
            value = m.group(1) or m.group(0)
            if pattern is CREDENTIAL and m.group(1) is not None and (placeholder(value) or reserved(m.group(2))):
                continue
            if pattern is SECRET_FIELD and (placeholder(value) or ENV_NAME.fullmatch(value)):
                continue
            yield "credential", value, None
            text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    for m in HOME_PATH.finditer(text):
        if meaningful(m.group(1)):
            yield "home path", m.group(0), m.group(1)
    for m in EMAIL.finditer(text):
        if m.group(1).lower() != "git" and not reserved(m.group(2)) and not placeholder(m.group(2)):
            yield "email", m.group(0), None
    for m in INTERNAL.finditer(text):
        if m.group(2).lower() == "local" and not (
                text[:m.start()].endswith(("://", "@")) or text[m.end():m.end() + 1] == ":"):
            continue
        yield "internal host", m.group(1), None
    for m in IPV4.finditer(text):
        if flagged_ip(m.group(1)):
            yield "IP address", m.group(1), None
    for m in ACTOR.finditer(text):
        if meaningful(m.group(1)):
            yield "actor label", m.group(0), m.group(1)
    for m in UUID.finditer(text):
        if len(set(m.group(0).lower().replace("-", ""))) > 2:
            yield "identifier", m.group(0), None
    for m in ARN.finditer(text):
        if m.group(1) not in ("123456789012", "000000000000", "111111111111"):
            yield "identifier", m.group(1), None
    for m in FIELD.finditer(text):
        if NAME_LIKE.fullmatch(m.group(2)) and not placeholder(m.group(2)):
            yield "named field", m.group(2), None


def b64_text(run):
    try:
        raw = base64.b64decode(run.replace("-", "+").replace("_", "/") + "=" * (-len(run) % 4), validate=True)
        plain = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return plain if sum(c.isprintable() or c.isspace() for c in plain) >= 0.9 * len(plain) else None


def variants(text):
    """The line as written, then any encoded text inside it, decoded."""
    yield text, ""
    if "%" in text and urllib.parse.unquote(text) != text:
        yield urllib.parse.unquote(text), " (percent-encoded)"
    for run in B64.findall(text):
        plain = b64_text(run)
        if plain:
            yield plain, " (base64)"


def name_regex(names, flags):
    """One pattern for the names, matched whole and with or without separators between their words."""
    parts = []
    for name in sorted(names, key=len, reverse=True):
        words = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)
        parts.append(r"[ \t_.-]?".join(map(re.escape, words)))
    return re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(parts), flags) if parts else None


def scan(lines, names, allow):
    """Findings in (where, text) lines. names is (matched in any case, matched as written); a name a shape
    reveals is looked for in every line too. A credential is never dropped, allowed or shown inside another finding."""
    found, derived, per_line = [], set(), []
    for where, text in lines:
        exempt = bool(COPYRIGHT.search(text) or (where.startswith("commit message:") and TRAILER.match(text)))
        hits = []
        for plain, how in variants(text):
            for kind, value, name in shapes(plain):
                if name:
                    derived.add(name)
                if not (exempt and kind == "email"):
                    hits.append((kind + how, value))
        per_line.append((where, text, exempt, hits))
    loose, exact = names
    patterns = [p for p in (name_regex(loose | derived, re.I), name_regex(exact, 0)) if p]
    for where, text, exempt, hits in per_line:
        if not exempt:
            hits += [("name", m.group(0)) for pattern in patterns for m in pattern.finditer(text)]
        kept = []
        for kind, value in sorted(set(hits), key=lambda hit: (not hit[0].startswith("credential"), -len(hit[1]), hit)):
            if not any(value.casefold() in other.casefold()
                       or (other_kind.startswith("credential") and other.casefold() in value.casefold())
                       for other_kind, other in kept):
                kept.append((kind, value))
        found += [Finding(where, kind, value) for kind, value in kept
                  if kind.startswith("credential") or value.casefold() not in allow]
    return found


def unquote_path(path):
    if path.startswith('"') and path.endswith('"'):
        return codecs.escape_decode(path[1:-1].encode())[0].decode("utf-8", "replace")
    return path


def added_lines(patch):
    """(path, line number, text) for each line a -U0 patch adds, and (path, 0, None) for each file it shows;
    in a merge, only lines new to every parent."""
    path, header, width, number = None, False, 1, 0
    for line in patch.split("\n"):
        if line.startswith(("diff --git ", "diff --cc ", "diff --combined ")):
            path, header = None, True
        elif line.startswith("@@"):
            header = False
            width = len(line) - len(line.lstrip("@")) - 1
            number = int(re.search(r" \+(\d+)", line).group(1))
        elif header:
            if line.startswith("+++ "):
                target = unquote_path(line[4:].rstrip("\t"))
                path = None if target == "/dev/null" else target.split("/", 1)[1]
                if path is not None:
                    yield path, 0, None
        elif path is not None and not line.startswith("\\"):
            prefix = line[:width]
            if "-" in prefix:
                continue
            if prefix == "+" * width:
                yield path, number, line[width:]
            number += 1


def raw_entries(raw):
    """(status, source blob, new blob, new mode, path) from git's -z raw output. A merge's combined output
    lists each path that differs from every parent, as A when it is new to all of them, with no source."""
    fields, i = raw.split("\0"), 0
    while i < len(fields) and fields[i].startswith(":"):
        meta = fields[i].split()
        parents = len(meta[0]) - len(meta[0].lstrip(":"))
        if parents > 1:
            blob = meta[2 * parents + 1]
            status = "D" if set(blob) == {"0"} else "A" if set(meta[-1]) == {"A"} else "M"
            yield status, None, blob, meta[parents], fields[i + 1]
            i += 2
        elif meta[4][0] in "RC":
            yield meta[4][0], meta[2], meta[3], meta[1], fields[i + 2]
            i += 3
        else:
            yield meta[4][0], meta[2], meta[3], meta[1], fields[i + 1]
            i += 2


def printable_runs(data):
    return [run.decode("ascii") for run in re.findall(rb"[\x20-\x7e]{4,}", data)]


def png_text(data):
    out, pos = [], 8
    while pos + 8 <= len(data):
        size, kind = int.from_bytes(data[pos:pos + 4], "big"), data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + size]
        pos += 12 + size
        if kind == b"tEXt":
            out.append(body.replace(b"\0", b" ").decode("latin-1"))
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            out.append(key.decode("latin-1") + " " + zlib.decompress(rest[1:]).decode("latin-1"))
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            text = rest[2:].split(b"\0", 2)[2]
            out.append(key.decode("latin-1") + " " + (zlib.decompress(text) if rest[0] else text).decode("utf-8"))
        elif kind == b"eXIf":
            out += printable_runs(body)
        elif kind == b"IEND":
            return out
    raise ValueError("no end chunk")


def jpeg_text(data):
    out, pos = [], 2
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xDA:
            return out
        size = int.from_bytes(data[pos + 2:pos + 4], "big")
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            out += printable_runs(data[pos + 4:pos + 2 + size])
        pos += 2 + size
    raise ValueError("no image data")


def shown(path):
    """The path as printed; one that holds a credential in any form is never printed."""
    hidden = any(kind == "credential" for text, _ in variants(path) for kind, _, _ in shapes(text))
    return "<a path holding a credential>" if hidden else path


def change_lines(patch, raw):
    """The lines a change adds, its new paths and the metadata of its images; every binary by blob id too."""
    lines, binaries, seen = [], [], set()
    for path, number, text in added_lines(patch):
        seen.add(path)
        if text is not None:
            lines.append(("%s:%d" % (shown(path), number), text))
    for status, source, blob, mode, path in raw_entries(raw):
        if status == "D" or mode == "160000":
            continue
        label = shown(path)
        if status in "ACR":
            lines.append(("%s: file name" % label, path))
        if path in seen or source == blob:
            continue
        data = git("cat-file", "blob", blob, binary=True)
        if b"\0" not in data[:8000]:
            if source is not None:  # a merge's new text lines are in its combined patch
                text = data.decode("utf-8", "replace")
                lines += [("%s:%d" % (label, n), line) for n, line in enumerate(text.splitlines(), 1)]
            continue
        try:
            meta = png_text(data) if data.startswith(b"\x89PNG\r\n\x1a\n") else \
                jpeg_text(data) if data.startswith(b"\xff\xd8") else None
        except (ValueError, IndexError, zlib.error, UnicodeDecodeError):
            meta = None
        binaries.append((label, blob))
        lines += [("%s: metadata" % label, text) for text in meta or ()]
    return lines, binaries


def message_lines(message, comments=True):
    """Message lines up to the scissors; without comments, the "#" lines Git may strip are left to the push."""
    lines = []
    for number, line in enumerate(message.split("\n"), 1):
        if SCISSORS.match(line):
            break
        if comments or not line.startswith("#"):
            lines.append(("commit message:%d" % number, line))
    return lines


def checked(lines, binaries, names, allow):
    return scan(lines, names, allow) + [Finding(path, "binary", blob) for path, blob in binaries
                                        if blob.casefold() not in allow]


def read_allow(rev):
    """The accepted values in .privacy-allow, staged (rev ":") or in a commit; None when there is no such file."""
    if rev == ":":
        listing = git("ls-files", "-s", "--", ALLOW).split()
        blob = listing[1] if listing else None
    else:
        listing = git("ls-tree", "--full-tree", rev, "--", ALLOW).split()
        blob = listing[2] if listing else None
    if blob is None:
        return None
    allow = set()
    for number, line in enumerate(git("cat-file", "blob", blob).splitlines(), 1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if CREDENTIAL.search(value) or SECRET_FIELD.search(value):
            raise AllowError("line %d of %s has a credential shape; that file is public, so remove the line"
                             % (number, ALLOW))
        allow.add(value.casefold())
    return allow


def tracked_text(rev):
    """The text of every file in commit rev; empty for None or an unborn HEAD."""
    try:
        tree = git("rev-parse", "--verify", "-q", "%s^{tree}" % rev).strip() if rev else None
    except GitError:
        tree = None
    if tree is None:
        return ""
    blobs = [entry.split()[2] for entry in git("ls-tree", "-r", "-z", tree).split("\0") if entry.split()[1:2] == ["blob"]]
    batch = subprocess.run(["git", "cat-file", "--batch"], input="\n".join(blobs).encode(), capture_output=True)
    if batch.returncode != 0:
        raise GitError("git cat-file --batch: %s" % batch.stderr.decode(errors="replace").strip()[:200])
    texts, data, pos = [], batch.stdout, 0
    while pos < len(data):
        end = data.index(b"\n", pos)
        header, pos = data[pos:end].split(), end + 1
        if len(header) == 3:
            body = data[pos:pos + int(header[2])]
            pos += int(header[2]) + 1
            if b"\0" not in body[:8000]:
                texts.append(body.decode("utf-8", "replace"))
    return "\n".join(texts)


def sibling_folders(public):
    """Names of the folders beside the repository's main checkout, none where they are hidden. A name the
    files of commit public already hold, such as a public tool or an ordinary word, is left out."""
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    if os.path.basename(common) != ".git":
        return []
    main = os.path.dirname(common)
    try:
        entries = list(os.scandir(os.path.dirname(main)))
    except (FileNotFoundError, PermissionError):
        return []
    names = [e.name for e in entries if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")
             and e.name != os.path.basename(main) and e.name.lower() not in GENERIC_FOLDERS and meaningful(e.name)]
    pattern = name_regex(set(names), re.I)
    present = {m.group(0) for m in pattern.finditer(tracked_text(public))} if pattern else set()
    return [n for n in names if not any(name_regex({n}, re.I).fullmatch(text) for text in present)]


def private_names():
    try:
        with open(os.path.expanduser("~/.config/agent-alignment/privacy-names"), encoding="utf-8") as names:
            return [line.strip() for line in names if line.strip() and not line.lstrip().startswith("#")]
    except (FileNotFoundError, PermissionError):
        return []


def machine_names(public):
    """Names read from this machine, matched in any case, and the words of the Git name, matched as written.
    public is a commit whose files show which folder names are already public, or None."""
    loose = {getpass.getuser(), socket.gethostname().split(".")[0], *sibling_folders(public), *private_names()}
    name = git("config", "--default", "", "user.name").strip()
    email = git("config", "--default", "", "user.email").strip()
    loose.update(value for value in (name, email, email.split("@")[0]) if value)
    return {n for n in loose if meaningful(n)}, {n for n in name.split() if meaningful(n)}


def head_or_empty():
    try:
        return git("rev-parse", "--verify", "-q", "HEAD^{commit}").strip()
    except GitError:
        return git("hash-object", "-t", "tree", "/dev/null").strip()


def check_staged(allow, names):
    base = head_or_empty()
    patch = git("diff-index", "--cached", "-p", "-U0", "-M", "--src-prefix=a/", "--dst-prefix=b/", base)
    lines, binaries = change_lines(patch, git("diff-index", "--cached", "-z", "-M", base))
    return checked(lines, binaries, names, allow)


def check_message(path, allow, names):
    with open(path, encoding="utf-8", errors="replace") as message:
        return checked(message_lines(message.read(), comments=False), [], names, allow)


def check_commit(sha, allow, names):
    merge = len(git("rev-list", "--parents", "-n", "1", sha).split()) > 2
    patch = git("diff-tree", "-p", "-U0", "-M", "--cc", "--root", "--no-commit-id",
                "--src-prefix=a/", "--dst-prefix=b/", sha)
    raw = git("diff-tree", "-r", "-z", "-c" if merge else "-M", "--root", "--no-commit-id", sha)
    lines, binaries = change_lines(patch, raw)
    lines += message_lines(git("log", "-1", "--format=%B", sha))
    return checked(lines, binaries, names, allow)


def check_push(ranges, public):
    """Findings in each pushed commit, oldest first, against the .privacy-allow at the tip of its ref. ranges
    holds (tip, the ref's commit on the remote or None, the commits pushed). public is a commit the remote
    already has, or None; never a commit being pushed."""
    found, seen, names = [], set(), None
    for tip, old, shas in ranges:
        allow = read_allow(tip)
        if allow is None:
            touched = shas and git("rev-list", "--no-walk", "--full-history", "--stdin", "--", ALLOW,
                                   stdin="\n".join(shas).encode()).strip()
            if touched or (old and read_allow(old) is not None):
                raise AllowError(REMOVED)
            continue
        names = machine_names(public) if names is None else names
        for sha in reversed(shas):
            if sha not in seen:
                seen.add(sha)
                found += [f._replace(where="%s %s" % (sha[:12], f.where)) for f in check_commit(sha, allow, names)]
    return found


def report(found, what):
    if not found:
        return 0
    print("Privacy check: %d finding(s), so Git cancelled the %s. Nothing was changed." % (len(found), what),
          file=sys.stderr)
    for f in found:
        value = "value not shown" if f.kind.startswith("credential") else f.value
        print("  %s: %s: %s  (%s)" % (f.where, f.kind, value, SUGGEST[f.kind.split(" (")[0]]), file=sys.stderr)
    print("Replace each and try again. A value that is public anyway, and is not a credential, can go on "
          "its own line in %s." % ALLOW, file=sys.stderr)
    return 1


def main(argv):
    os.environ["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    try:
        allow = read_allow(":")
        if allow is None:
            if read_allow(head_or_empty()) is None:
                return 0
            raise AllowError(REMOVED)
        if argv[1:] == ["staged"]:
            found = check_staged(allow, machine_names("HEAD"))
        elif len(argv) == 3 and argv[1] == "message":
            found = check_message(argv[2], allow, machine_names("HEAD"))
        else:
            print("usage: privacy_check.py staged | message <file>", file=sys.stderr)
            return 2
    except (GitError, AllowError) as err:
        print("Privacy check could not run (%s); commit refused." % err, file=sys.stderr)
        return 1
    return report(found, "commit")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
