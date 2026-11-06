#!/usr/bin/env python3
"""PreToolUse guard: agents never act outside this machine and never read secrets.

Blocks pushes, GitHub writes, cluster and host changes, cloud writes, external
posts, secret reads and shell writes to guardrail files. Sends back commit
messages and shell-written docs that carry AI tells. The OS sandbox is the hard
boundary; this guard gives fast, clear refusals on top of it.
"""
import json
import os
import re
import shlex
import sys
import urllib.parse

REASON = (
    "Blocked by the user's standing rule: agents never act outside this machine "
    "(push, PR, review, comment, merge, cluster, hosts, cloud, Slack, email) and "
    "never read secret values. Stop. Tell the user what was blocked and why you "
    "wanted it, and let the user decide whether it should happen at all. Do not hand "
    "it over as a routine step to run, and do not retry it another way."
)

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SHELL_WORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{", "}",
               "function", "coproc"}
WRAPPERS = {"sudo", "env", "nohup", "time", "nice", "ionice", "stdbuf", "command",
            "exec", "builtin", "watch", "unbuffer", "chronic", "doas"}
WRAPPER_ARGS = {"sudo": {"-u", "-g", "-h", "-C", "-p", "-U"}, "doas": {"-u", "-C"},
                "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "env": {"-u", "-C"},
                "timeout": {"-s", "-k", "--signal", "--kill-after"}}
READERS = {"cat", "head", "tail", "less", "more", "sed", "awk", "gawk", "grep", "egrep",
           "rg", "cp", "base64", "xxd", "strings", "od", "vim", "vi", "nano", "jq", "yq",
           "bat", "tac", "nl", "hexdump", "diff", "source", "."}
SECRET_PATH = re.compile(
    r"(\.tfvars(\.json)?$|\.tfstate|\.age$|\.kdbx$|kubeconfig|/\.kube/|/\.ssh/|"
    r"id_(rsa|ed25519|ecdsa)|\.pem$|\.key$|(^|/)\.env(\.|$)|(^|/)\.envrc$|"
    r"credentials|\.netrc$|vault-init|unseal|[-_.]token$|(access|secret)[-_]key$|"
    r"/\.password-store/|/\.config/gh/|/\.aws/|/\.config/[^/\s]+/[^/\s]*\.env$)"
)
TEMPLATE_OK = re.compile(r"\.(example|sample|template|dist|md|sh|py|go|j2|pub)$")
GUARDRAIL_PATH = re.compile(
    r"(\.claude/(settings(\.local)?\.json|CLAUDE\.md|hooks/|scripts/|agents/|commands/)|"
    r"\.codex/(AGENTS\.md|rules/|config\.toml)|/etc/claude-code)"
)
LOCAL_HOSTS = re.compile(
    r"^https?://(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\]|[\w.-]+\.localhost|"
    r"host\.docker\.internal)(:(\d+|\$\{?\w+\}?))?(/|$)"
)
NOTIFY_HOSTS = re.compile(
    r"(slack\.com|hooks\.slack|discord(app)?\.com/api/webhooks|api\.sendgrid|mailgun|"
    r"api\.postmarkapp|smtp\.)"
)
AWS_WRITE = re.compile(
    r"^(put|delete|create|update|modify|terminate|run|start|stop|reboot|attach|detach|"
    r"associate|disassociate|restore|tag|untag|set|register|deregister|send|publish|"
    r"invoke|import|copy|enable|disable|reset|revoke|authorize|replace|cancel|change|"
    r"add|remove|upload|complete|abort|batch|rotate|merge|accept|reject)"
)
ASSIGN_RX = re.compile(
    r"(?:^|[\s;&|(])(?:export\s+|local\s+|readonly\s+|declare\s+(?:-\w+\s+)?)?"
    r"([A-Za-z_]\w*)=(?:\"((?:[^\"\\]|\\.)*)\"|'([^']*)'|([^\s;&|)]*))"
)
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][\w-]*)\1")
DOC_TARGET = re.compile(r"(>>?|\btee\b(\s+-a)?)\s*['\"]?([^\s'\";&|]+\.(md|txt|rst|adoc|html))\b")
WRITE_TARGET = "__write_target__"
READ_SOURCE = "__read_source__"
ASSIGN = {}
DEPTH = [0]


class Blocked(Exception):
    pass


class Rewrite(Exception):
    pass


def deny(what):
    raise Blocked(what)


try:
    from tells_check import find_tells
except ImportError:
    def find_tells(text):
        return []


def heredocs(cmd):
    """Every heredoc as (opening line, body)."""
    lines, i, out = cmd.split("\n"), 0, []
    while i < len(lines):
        line = lines[i]
        i += 1
        for _, delim in HEREDOC.findall(line):
            body = []
            while i < len(lines) and lines[i].strip() != delim:
                body.append(lines[i])
                i += 1
            i += 1
            out.append((line, "\n".join(body)))
    return out


def strip_heredocs(cmd):
    """Remove heredoc bodies; return (text, bodies fed to a shell)."""
    out, shell_bodies = [], []
    lines = cmd.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = HEREDOC.findall(line)
        i += 1
        if not delims:
            continue
        before = re.split(r"(?<!<)<<(?!<)", line, maxsplit=1)[0].rstrip()
        to_shell = bool(re.search(r"(^|[\s|;&(])(%s)(\s+-[\w-]+)*$" % "|".join(SHELLS),
                                  before))
        for _, delim in delims:
            body = []
            while i < len(lines) and lines[i].strip() != delim:
                body.append(lines[i])
                i += 1
            i += 1
            if to_shell:
                shell_bodies.append("\n".join(body))
    return "\n".join(out), shell_bodies


def strip_comments(text):
    """Drop shell comments: '#' at the start of a word, outside quotes, to end of line."""
    out = []
    for line in text.split("\n"):
        quote, esc, cut = None, False, None
        for i, ch in enumerate(line):
            if esc:
                esc = False
                continue
            if ch == "\\" and quote != "'":
                esc = True
                continue
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                continue
            if ch == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def segments(cmd):
    """Simple commands, plus redirect targets as pseudo-commands."""
    text, shell_bodies = strip_heredocs(cmd)
    text = strip_comments(text).replace("`", "\n").replace("\n", " ; ")
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        tokens = text.split()
    seg, pending = [], None
    for tok in tokens:
        if pending is not None:
            if pending:
                yield [pending, tok]
            pending = None
            continue
        if tok and set(tok) <= set(";&|()<>"):
            if seg:
                yield seg
            seg = []
            if "<<" in tok:
                pending = ""
            elif tok.endswith(("<", "<&", "<>")):
                pending = READ_SOURCE
            elif tok.endswith((">", ">>", ">&", ">|")):
                pending = WRITE_TARGET
        elif tok == "$":
            continue
        else:
            seg.append(tok)
    if seg:
        yield seg
    for body in shell_bodies:
        yield from segments(body)


def unwrap(argv):
    while argv:
        while argv and argv[0] in SHELL_WORDS:
            argv = argv[1:]
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv = argv[1:]
        if not argv:
            return argv
        name = os.path.basename(argv[0])
        if name == "command" and argv[1:2] in (["-v"], ["-V"]):
            return []
        if name in WRAPPERS or name == "timeout":
            takes = WRAPPER_ARGS.get(name, ())
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                flag, argv = argv[0], argv[1:]
                if flag in takes and argv:
                    argv = argv[1:]
            if name == "timeout":
                argv = argv[1:]
            continue
        if name == "xargs":
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                flag = argv[0]
                argv = argv[1:]
                if flag in ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a") and argv:
                    argv = argv[1:]
            continue
        return argv
    return argv


def positional(args, takes_value=()):
    """Non-option arguments, skipping values of known value-taking options."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            if a in takes_value:
                skip = True
            continue
        out.append(a)
    return out


def file_operands(name, args):
    """The files a reader command opens, leaving out search patterns and programs."""
    one = {"grep": {"-e", "-f", "-m", "-A", "-B", "-C", "-d", "-D", "--regexp", "--file",
                    "--max-count"},
           "rg": {"-e", "-f", "-m", "-A", "-B", "-C", "-g", "-t", "-T", "--regexp", "--file",
                  "--glob", "--type", "--type-not", "--max-count"},
           "sed": {"-e", "-f", "-l", "--expression", "--file"},
           "awk": {"-f", "-v", "-F", "--file", "--assign", "--field-separator"},
           "jq": {"-f", "--from-file", "--indent"},
           "head": {"-n", "-c"}, "tail": {"-n", "-c"}}
    two = {"jq": {"--arg", "--argjson", "--slurpfile", "--rawfile"}}
    key = {"egrep": "grep", "gawk": "awk", "yq": "jq"}.get(name, name)
    takes_one, takes_two = one.get(key, set()), two.get(key, set())
    files, rest, i = [], [], 0
    explicit = False
    while i < len(args):
        a = args[i]
        if a in takes_two:
            if a in ("--slurpfile", "--rawfile") and i + 2 < len(args):
                files.append(args[i + 2])
            i += 3
            continue
        if a in takes_one:
            if a in ("-e", "--regexp", "--expression") or (key == "awk" and a in ("-f", "--file")) \
                    or (key == "jq" and a in ("-f", "--from-file")):
                explicit = True
            if a in ("-f", "--file", "--from-file") and i + 1 < len(args):
                files.append(args[i + 1])
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        rest.append(a)
        i += 1
    if key in ("grep", "rg", "sed", "awk", "jq") and not explicit and rest:
        rest = rest[1:]
    return files + rest


def secret_file(path):
    return bool(SECRET_PATH.search(path)) and (
        not TEMPLATE_OK.search(path) or bool(re.search(r"/\.(kube|ssh)/", path)))


def check_git(args):
    pos = positional(args, {"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
    if not pos:
        return
    sub = pos[0]
    if sub in ("push", "send-email", "request-pull"):
        deny("git " + sub)
    if sub in ("commit", "merge", "rebase", "am") and "--no-verify" in args:
        deny("git %s --no-verify" % sub)
    if sub == "commit":
        for i, arg in enumerate(args):
            path = args[i + 1] if arg in ("-F", "--file") and i + 1 < len(args) else None
            if arg.startswith("--file="):
                path = arg.split("=", 1)[1]
            if path and secret_file(path):
                deny("reading a secret as a commit message")
        tells = find_tells(commit_message(args))
        if tells:
            raise Rewrite("Commit message has AI tells: %s. Rewrite it in plain words, the way "
                          "the user writes, and commit again." % ", ".join(tells))


def commit_message(args):
    msgs = []
    for i, a in enumerate(args):
        if (a in ("-m", "--message") or re.fullmatch(r"-[a-zA-Z]*m", a)) and i + 1 < len(args):
            msgs.append(args[i + 1])
        elif a.startswith("--message="):
            msgs.append(a.split("=", 1)[1])
    return "\n".join(msgs)


def check_gh(args):
    pos = positional(args, {"-R", "--repo", "--hostname"})
    if not pos:
        return
    group = pos[0]
    action = pos[1] if len(pos) > 1 else ""
    writes = {
        "pr": {"create", "merge", "review", "comment", "close", "edit", "ready",
               "reopen", "lock", "unlock", "update-branch"},
        "issue": {"create", "comment", "close", "edit", "reopen", "delete",
                  "transfer", "lock", "unlock", "pin", "unpin", "develop"},
        "release": {"create", "edit", "delete", "upload", "delete-asset"},
        "repo": {"create", "delete", "edit", "rename", "archive", "unarchive",
                 "fork", "sync", "deploy-key", "set-default"},
        "workflow": {"run", "enable", "disable"},
        "run": {"rerun", "cancel", "delete"},
        "secret": {"set", "delete", "remove"},
        "variable": {"set", "delete"},
        "label": {"create", "edit", "delete", "clone"},
        "gist": {"create", "edit", "delete", "clone"},
        "ruleset": {"create", "edit", "delete"},
        "cache": {"delete"},
        "project": {"create", "edit", "delete", "item-add", "item-edit",
                    "item-delete", "item-create", "close", "copy", "link", "unlink"},
        "alias": {"set", "import"},
        "auth": {"token"},
    }
    if group in writes and action in writes[group]:
        deny("gh %s %s" % (group, action))
    if group == "api":
        method = None
        has_fields = False
        endpoint = action
        for i, a in enumerate(args):
            if a in ("-X", "--method") and i + 1 < len(args):
                method = args[i + 1].upper()
            elif a.startswith("--method="):
                method = a.split("=", 1)[1].upper()
            elif a.startswith("-X") and len(a) > 2:
                method = a[2:].upper()
            elif a in ("-f", "-F", "--field", "--raw-field", "--input") or \
                    a.startswith(("--field=", "--raw-field=", "--input=")):
                has_fields = True
        if method and method not in ("GET", "HEAD"):
            deny("gh api -X " + method)
        if has_fields and method is None:
            if endpoint == "graphql":
                if re.search(r"\bmutation\b", " ".join(args)):
                    deny("gh api graphql mutation")
            else:
                deny("gh api with fields (implies POST)")


def check_kubectl(args):
    if any(a in ("-h", "--help") for a in args):
        return
    if any(a.startswith("--dry-run=client") for a in args) or "--local" in args:
        return
    pos = positional(args, {"-n", "--namespace", "--context", "--kubeconfig",
                            "--cluster", "--user", "-s", "--server", "--as",
                            "--token", "-l", "--selector", "-o", "--output",
                            "-f", "--filename", "-c", "--container", "--field-selector"})
    if not pos:
        return
    verb = pos[0]
    writes = {"apply", "create", "delete", "patch", "edit", "replace", "scale",
              "annotate", "label", "cordon", "drain", "uncordon", "taint", "set",
              "exec", "cp", "debug", "run", "expose", "autoscale", "attach",
              "certificate", "kustomize-apply"}
    if verb in writes:
        deny("kubectl " + verb)
    if verb == "rollout" and len(pos) > 1 and pos[1] not in ("status", "history"):
        deny("kubectl rollout " + pos[1])
    joined = " ".join(args)
    if verb == "get":
        res = pos[1] if len(pos) > 1 else ""
        secret = any(r in ("secret", "secrets") or r.startswith(("secret/", "secrets/"))
                     for r in res.split(","))
        names_only = re.search(r"(-o|--output)[= ]?\s*name\b", joined) or (
            re.search(r"jsonpath|custom-columns", joined)
            and not re.search(r"\.data|stringData", joined))
        if secret and not names_only and re.search(
                r"(-o|--output)[= ]?\s*(yaml|json|jsonpath|go-template|custom)", joined):
            deny("kubectl get secret with values")
    if verb == "config" and re.search(r"--raw|--flatten", joined):
        deny("kubectl config view --raw")


def check_argocd(args):
    pos = positional(args, {"--server", "--grpc-web-root-path", "--auth-token",
                            "--config", "-o", "--output"})
    reads = {("app", "get"), ("app", "list"), ("app", "diff"), ("app", "history"),
             ("app", "manifests"), ("app", "resources"), ("app", "logs"),
             ("app", "wait"), ("proj", "list"), ("proj", "get"), ("repo", "list"),
             ("cluster", "list"), ("cluster", "get"), ("account", "get-user-info")}
    if not pos or pos[0] in ("version", "login", "logout", "context", "completion"):
        return
    if pos[:3] == ["admin", "settings", "rbac"]:
        return
    if (pos[0], pos[1] if len(pos) > 1 else "") not in reads:
        deny("argocd " + " ".join(pos[:2]))


def check_terraform(args):
    pos = positional(args, {"-chdir", "-var", "-var-file", "-target"})
    if not pos:
        return
    sub = pos[0]
    if sub in ("apply", "destroy", "import", "taint", "untaint", "force-unlock",
               "output", "show", "console", "refresh"):
        deny("terraform " + sub)
    if sub == "state" and len(pos) > 1 and pos[1] not in ("list",):
        deny("terraform state " + pos[1])
    if sub == "workspace" and len(pos) > 1 and pos[1] in ("delete", "new"):
        deny("terraform workspace " + pos[1])


def check_aws(args):
    pos = positional(args, {"--profile", "--region", "--output", "--endpoint-url",
                            "--query", "--color", "--ca-bundle", "--cli-read-timeout",
                            "--cli-connect-timeout"})
    if len(pos) < 2:
        return
    service, action = pos[0], pos[1]
    if service == "s3" and action in ("cp", "mv", "rm", "sync", "mb", "rb", "website"):
        deny("aws s3 " + action)
    if AWS_WRITE.match(action):
        deny("aws %s %s" % (service, action))
    if (service, action) in (("secretsmanager", "get-secret-value"),
                             ("ssm", "get-parameter"), ("ssm", "get-parameters"),
                             ("ssm", "get-parameters-by-path"), ("kms", "decrypt")):
        deny("aws %s %s" % (service, action))


def check_http(name, args):
    def expand(a):
        for var, vals in ASSIGN.items():
            if vals and re.match(r"^https?://", vals[-1]) and ("$" + var) in a:
                a = a.replace("${%s}" % var, vals[-1]).replace("$" + var, vals[-1])
        return a
    args = [expand(a) for a in args]
    urls = [a for a in args if re.match(r"^https?://", a)]
    joined = " ".join(args)
    if any(NOTIFY_HOSTS.search(u) for u in urls) or NOTIFY_HOSTS.search(joined):
        deny(name + " to a messaging or mail service")
    if any(a in ("-G", "--get") for a in args) and not any(a in ("-X", "--request") for a in args):
        return
    write = False
    for i, a in enumerate(args):
        if a in ("-X", "--request") and i + 1 < len(args):
            write = args[i + 1].upper() not in ("GET", "HEAD", "OPTIONS")
        elif a.startswith("-X") and len(a) > 2 and name == "curl":
            write = a[2:].upper() not in ("GET", "HEAD", "OPTIONS")
        elif a in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode",
                   "-F", "--form", "-T", "--upload-file", "--json") or \
                a.startswith(("--data", "--form", "--json", "--post-data", "--post-file",
                              "--method", "--body-data", "--body-file")):
            write = True
        if write:
            break
    if name in ("http", "https", "xh") and len(args) > 0 and \
            args[0].upper() in ("POST", "PUT", "PATCH", "DELETE"):
        write = True
    if write and any(not LOCAL_HOSTS.match(u) for u in urls):
        deny(name + " write to a remote host")


def check_guardrail_writes(name, args):
    if name in ("cp", "mv", "install", "ln", "rsync"):
        targets = [a for a in args if not a.startswith("-")][-1:]
    elif name in ("rm", "chmod", "chown", "truncate", "tee", "unlink", "shred"):
        targets = [a for a in args if not a.startswith("-")]
    elif name == "dd":
        targets = [a[3:] for a in args if a.startswith("of=")]
    elif name in ("sed", "perl") and any(a.startswith("-i") or a.startswith("--in-place")
                                         or (name == "perl" and re.fullmatch(r"-\w*i\w*", a))
                                         for a in args):
        targets = file_operands("sed", args) if name == "sed" else \
            [a for a in args if not a.startswith("-")][1:]
    else:
        return
    if any(GUARDRAIL_PATH.search(t) for t in targets):
        deny("changing an agent guardrail from the shell")


def check_argv(argv):
    argv = unwrap(list(argv))
    if not argv:
        return
    if argv[0] == WRITE_TARGET:
        if GUARDRAIL_PATH.search(argv[1]):
            deny("changing an agent guardrail from the shell")
        return
    if argv[0] == READ_SOURCE:
        if secret_file(argv[1]):
            deny("reading a secret file")
        return
    var = re.match(r"^\$\{?([A-Za-z_]\w*)\}?$", argv[0])
    if var and ASSIGN.get(var.group(1)) and DEPTH[0] < 4:
        DEPTH[0] += 1
        try:
            for val in ASSIGN[var.group(1)]:
                try:
                    head = shlex.split(val)
                except ValueError:
                    head = val.split()
                if head and not re.match(r"^\$\{?%s\}?$" % var.group(1), head[0]):
                    check_argv(head + argv[1:])
        finally:
            DEPTH[0] -= 1
    name = os.path.basename(argv[0])
    args = argv[1:]
    if name in SHELLS or name == "eval":
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:] and i + 1 < len(args):
                check_command(args[i + 1])
                return
        if name == "eval":
            check_command(" ".join(args))
        return
    if name == "su" and "-c" in args:
        idx = args.index("-c")
        if idx + 1 < len(args):
            check_command(args[idx + 1])
        return
    if name == "find":
        for i, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                rest = []
                for b in args[i + 1:]:
                    if b in (";", "\\;", "+"):
                        break
                    rest.append(b)
                check_argv(rest)
    check_guardrail_writes(name, args)
    if name == "git":
        check_git(args)
        if "credential" in args[:3] and any(a in ("fill", "get") for a in args):
            deny("git credential fill")
    elif name == "gh":
        check_gh(args)
    elif name in ("kubectl", "k", "oc", "kubecolor", "k8s.sh"):
        check_kubectl(args)
    elif name == "helm":
        if any(a in ("-h", "--help") for a in args):
            return
        pos = positional(args, {"-n", "--namespace", "--kube-context", "--kubeconfig"})
        if pos and pos[0] in ("install", "upgrade", "uninstall", "delete", "rollback",
                              "push", "repo-add"):
            deny("helm " + pos[0])
    elif name == "argocd":
        check_argocd(args)
    elif name in ("ansible-playbook", "ansible", "ansible-pull", "ansible-console"):
        if not any(a in ("--syntax-check", "--list-hosts", "--list-tasks", "--list-tags",
                         "--version", "-h", "--help") for a in args):
            deny(name)
    elif name == "ansible-vault":
        pos = positional(args)
        if pos and pos[0] in ("view", "decrypt", "edit", "rekey"):
            deny("ansible-vault " + pos[0])
    elif name in ("ssh", "scp", "sftp", "mosh", "ssh-copy-id", "autossh", "sshpass"):
        if not (name == "ssh" and any(a in ("-V", "-G") for a in args)):
            deny(name)
    elif name == "tailscale":
        pos = positional(args)
        if pos and pos[0] in ("ssh", "file", "funnel", "serve"):
            deny("tailscale " + pos[0])
    elif name == "rsync":
        if any(re.match(r"^([\w.-]+@)?[\w.-]+:", a) or a.startswith("rsync://")
               for a in args if not a.startswith("-")):
            deny("rsync to a remote host")
    elif name in ("terraform", "tofu", "terragrunt"):
        check_terraform(args)
    elif name == "vault":
        if any(a in ("-h", "--help", "-help") for a in args) or \
                (args[:1] == ["server"] and "-dev" in args):
            return
        pos = positional(args, {"-address", "-namespace", "-format"})
        if pos and pos[0] not in ("status", "version", "-version"):
            deny("vault " + pos[0])
    elif name == "aws":
        check_aws(args)
    elif name == "doctl":
        pos = positional(args)
        if pos and pos[0] != "version":
            deny("doctl")
    elif name in ("curl", "wget", "http", "https", "xh", "httpie"):
        check_http(name, args)
    elif name in ("docker", "podman", "buildah", "skopeo", "crane", "oras"):
        pos = positional(args)
        if pos and (pos[0] in ("push", "copy") or pos[:2] in (["image", "push"],
                                                              ["manifest", "push"])):
            deny(name + " push")
    elif name in ("npm", "pnpm", "yarn", "cargo", "gem", "poetry", "flit", "hatch"):
        pos = positional(args)
        if pos and pos[0] in ("publish", "push", "unpublish", "deprecate", "yank"):
            deny(name + " " + pos[0])
    elif name == "twine":
        deny("twine")
    elif name in ("mail", "mailx", "sendmail", "mutt", "msmtp", "swaks", "s-nail"):
        deny(name)
    elif name in ("age", "rage"):
        if "-d" in args or "--decrypt" in args:
            deny("age decrypt")
    elif name == "sops":
        if any(a in ("-d", "--decrypt", "exec-env", "exec-file", "decrypt", "edit")
               for a in args):
            deny("sops decrypt")
    elif name in ("gpg", "gpg2"):
        if any(a in ("-d", "--decrypt", "--export-secret-keys") for a in args):
            deny("gpg decrypt")
    elif name in ("keepassxc-cli", "kpcli"):
        pos = positional(args)
        if pos and pos[0] in ("show", "clip", "export", "totp", "attachment-export",
                              "search", "ls", "db-info"):
            deny(name + " " + pos[0])
    elif name in ("pass", "gopass", "bw", "op", "lpass"):
        deny(name)
    if name in READERS:
        if any(secret_file(f) for f in file_operands(name, args)):
            deny("reading a secret file")


def check_command(cmd):
    text, shell_bodies = strip_heredocs(cmd)
    for part in [text] + shell_bodies:
        if IRREVERSIBLE.search(code_view(part)):
            deny("irreversible command")
    for seg in segments(cmd):
        check_argv(seg)


def check_tells(cmd):
    """Commit messages and docs written through the shell must read as the user's."""
    bodies = heredocs(cmd)
    if re.search(r"\bgit\b[^;&|\n]*\bcommit\b", cmd):
        texts = [body for line, body in bodies if re.search(r"\bcommit\b", line)]
        tells = find_tells("\n".join(texts))
        if tells:
            raise Rewrite("Commit message has AI tells: %s. Rewrite it in plain words, the way "
                          "the user writes, and commit again." % ", ".join(tells))
    for line, body in bodies:
        target = DOC_TARGET.search(line)
        if target and not target.group(3).startswith("/tmp/"):
            tells = find_tells(body)
            if tells:
                raise Rewrite("%s has AI tells: %s. Rewrite those lines in plain words, the way "
                              "the user writes." % (target.group(3), ", ".join(tells)))


FALLBACK = re.compile(
    r"\bgit\b[^;&|\n]*\bpush\b|\bgh\s+(pr|issue|release)\s+(create|merge|review|"
    r"comment|close|edit)\b|\bkubectl\b[^;&|\n]*\b(apply|delete|patch|edit|scale)\b|"
    r"\bansible-playbook\b|(^|[;&|\s])ssh\s|hooks\.slack"
)

# Irreversible commands the retired shell guard blocked outright; still denied here.
IRREVERSIBLE = re.compile(
    r"\brm\s+-(rf|fr)\s+\*|\b(curl|wget)\b[^|\n]*\|\s*(sudo\b|(ba|z|da)?sh(\s|$|[)`;&|]))|"
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"
)

MCP_WRITE = re.compile(
    r"^mcp__.*(gmail|slack|github|mail|calendar|drive|docs|notion|linear|jira).*__"
    r"(?:[a-z0-9]+[_-])*(send|post|reply|create|update|delete|merge|comment|push|share|publish|draft|"
    r"batch|upload|move|invite|edit|add|remove|label|archive)",
    re.IGNORECASE,
)

# MCP servers run outside the Bash sandbox, so a browser one of them drives has
# the user's network. Browser tools may only be pointed at this machine.
BROWSER_SERVER = re.compile(r"playwright|puppeteer|chrom|browser|devtools|selenium|webdriver|webresearch", re.IGNORECASE)
URL_RX = re.compile(r"\b(?:https?|wss?|ftp|file)://[^\s'\"`<>()]+", re.IGNORECASE)


def off_machine(value):
    """The first URL in a browser tool's input that does not point at this machine, or None."""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        for item in value:
            hit = off_machine(item)
            if hit:
                return hit
    elif isinstance(value, str):
        for m in URL_RX.finditer(value):
            if not LOCAL_HOSTS.match(re.sub(r"^wss?://", "http://", m.group(0), flags=re.IGNORECASE)):
                return m.group(0)
    return None


def code_view(text):
    """The command without heredoc bodies, comments and quoted text: what the
    shell would run, for pattern checks that must not fire on data. Command
    substitutions inside double quotes still run, so they stay."""
    text = strip_comments(strip_heredocs(text)[0])

    def inert(m):
        if m.group(0).startswith("'"):
            return "''"
        return " ".join(re.findall(r"\$\([^)]*\)|`[^`]*`", m.group(0))) or "''"
    return re.sub(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"", inert, text)


def decide(cmd):
    """Check one shell command. Raises Blocked or Rewrite."""
    ASSIGN.clear()
    DEPTH[0] = 0
    for m in ASSIGN_RX.finditer(strip_heredocs(cmd)[0]):
        val = next(v for v in m.groups()[1:] if v is not None)
        ASSIGN.setdefault(m.group(1), []).append(val)
    check_tells(cmd)
    try:
        check_command(cmd)
    except (Blocked, Rewrite):
        raise
    except Exception:
        if FALLBACK.search(cmd):
            deny("unparsed outward command")


# WebFetch runs outside the sandbox and its network allowlist, so it may read
# only the hosts in fetch_allow.txt and fetch_allow.local.txt beside this file.
# The length limits cap how much a URL can carry; any listed host can still
# receive a little data in a query. Without fetch_allow.txt every fetch is
# refused.
FETCH_LISTS = ("fetch_allow.txt", "fetch_allow.local.txt")
FETCH_MAX_QUERY = 200
FETCH_MAX_URL = 1024


def fetch_hosts():
    here = os.path.dirname(os.path.abspath(__file__))
    hosts = set()
    for i, name in enumerate(FETCH_LISTS):
        try:
            with open(os.path.join(here, name)) as f:
                lines = f.read().splitlines()
        except OSError:
            if i == 0:
                deny("WebFetch: the reading list %s is missing" % os.path.join(here, name))
            continue
        hosts.update(line.split("#", 1)[0].strip().lower() for line in lines)
    hosts.discard("")
    return hosts


def check_fetch(url):
    url = url or ""
    parts = urllib.parse.urlsplit(url)
    # Python and the client can read a URL with a backslash or a user@ part as
    # different hosts, so refuse those.
    if (parts.scheme not in ("http", "https") or "\\" in url or "@" in parts.netloc
            or ":" in parts.netloc or any(c.isspace() or ord(c) < 32 for c in url)):
        deny("a fetch URL with a backslash, credentials, a port or an unusual scheme")
    host = (parts.hostname or "").lower().rstrip(".")
    if not any(host == d or host.endswith("." + d) for d in fetch_hosts()):
        deny("fetching %s, which is not on the reading list" % (host or "an unreadable URL"))
    if len(parts.query) > FETCH_MAX_QUERY or len(url) > FETCH_MAX_URL:
        deny("a fetch URL longer than the guard allows")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Guard could not read the tool call, so it was refused.",
        }}))
        return
    tool = data.get("tool_name", "")
    tin = data.get("tool_input") or {}
    try:
        if tool in ("Bash", "Monitor"):
            decide(tin.get("command", ""))
        elif tool == "WebFetch":
            check_fetch(tin.get("url", ""))
        elif MCP_WRITE.match(tool):
            deny(tool)
        elif tool.count("__") >= 2 and BROWSER_SERVER.search(tool.split("__")[1]):
            hit = off_machine(tin)
            if hit:
                deny("%s: browser tools stay on this machine, not %s" % (tool, hit))
    except Rewrite as r:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": str(r),
            }
        }))
    except Blocked as b:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "%s [%s]" % (REASON, b),
            }
        }))


if __name__ == "__main__":
    main()
