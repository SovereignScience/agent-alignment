#!/usr/bin/env bash
# PreToolUse hook for Bash. Block destructive patterns the project never
# wants run silently. Exit 0 = allow. Exit 2 = block (stderr → Claude).
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("tool_input",{}).get("command",""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

[[ -z "$cmd" ]] && exit 0

fixed_patterns=(
  'rm -rf /'
  'rm -rf ~'
  'git push'
  'git push --force'
  'git push -f '
  '--no-verify'
  '--no-gpg-sign'
  'git reset --hard origin/main'
  'git reset --hard origin/master'
  'chmod -R 777'
  ':(){ :|:& };:'
)
for pat in "${fixed_patterns[@]}"; do
  if printf '%s' "$cmd" | grep -Fq -- "$pat"; then
    {
      echo "pre-bash-guard: blocked literal pattern '$pat'"
      echo "Stop and explain the blocked action. Do not retry or delegate it."
    } >&2
    exit 2
  fi
done

regex_patterns=(
  'rm -rf \*'
  '(curl|wget)[^|]+\|[[:space:]]*sudo'
  '(curl|wget)[^|]+\|[[:space:]]*(ba)?sh([[:space:]]|$)'
)
for pat in "${regex_patterns[@]}"; do
  if printf '%s' "$cmd" | grep -Eq -- "$pat"; then
    {
      echo "pre-bash-guard: blocked regex pattern '$pat'"
      echo "Stop and explain the blocked action. Do not retry or delegate it."
    } >&2
    exit 2
  fi
done


if ! printf '%s' "$cmd" | /usr/bin/python3 -I -c '
import os, re, shlex, sys


def command_substitutions(text):
    def end(start, closing, nesting):
        if nesting > 32:
            raise ValueError("command substitution nested too deeply")
        quote, depth, i = None, 1, start
        while i < len(text):
            char = text[i]
            if char == "\\" and quote != chr(39):
                i += 2
                continue
            if quote == chr(39):
                if char == quote:
                    quote = None
            elif text.startswith("$(", i):
                i = end(i + 2, ")", nesting + 1)
            elif char == "`":
                if closing == "`":
                    return i
                i = end(i + 1, "`", nesting + 1)
            elif char in (chr(39), chr(34)):
                if quote is None:
                    quote = char
                elif char == quote:
                    quote = None
            elif quote is None:
                if char == "(" and closing == ")":
                    depth += 1
                elif char == closing:
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        raise ValueError("unterminated command substitution")

    quote, i = None, 0
    while i < len(text):
        char = text[i]
        if char == "\\" and quote != chr(39):
            i += 2
            continue
        if quote == chr(39):
            if char == quote:
                quote = None
        elif text.startswith("$(", i) or char == "`":
            start, closing = (i + 2, ")") if char == "$" else (i + 1, "`")
            stop = end(start, closing, 1)
            yield text[start:stop]
            i = stop
        elif char in (chr(39), chr(34)):
            if quote is None:
                quote = char
            elif char == quote:
                quote = None
        i += 1


def check(command, depth=0):
    if depth > 16:
        return False
    try:
        for body in command_substitutions(command):
            if not check(body, depth + 1):
                return False
    except ValueError:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return not re.search(r"\bgh\s+api\b", command)
    segments, argv = [], []
    for token in tokens + [";"]:
        if token and set(token) <= set(";&|()<>"):
            if argv:
                segments.append(argv)
            argv = []
        else:
            argv.append(token)
    for argv in segments:
        while argv and re.match(r"^[A-Za-z_]\w*=", argv[0]):
            argv = argv[1:]
        while argv and os.path.basename(argv[0]) in ("sudo", "env", "command", "exec", "nohup", "doas"):
            wrapper, argv = os.path.basename(argv[0]), argv[1:]
            while argv and argv[0].startswith("-"):
                flag, argv = argv[0], argv[1:]
                if wrapper == "env" and (flag.startswith("--split-string") or
                        (flag.startswith("-") and not flag.startswith("--") and "S" in flag)):
                    return False
                if flag in ("-u", "-g", "-C", "-h", "--user", "--group", "--chdir") and argv:
                    argv = argv[1:]
            while argv and re.match(r"^[A-Za-z_]\w*=", argv[0]):
                argv = argv[1:]
        if not argv:
            continue
        name, args = os.path.basename(argv[0]), argv[1:]
        if name in ("bash", "sh", "zsh", "dash", "ksh"):
            for i, arg in enumerate(args):
                if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:] and i + 1 < len(args):
                    if not check(args[i + 1], depth + 1):
                        return False
        if name != "gh":
            continue
        while args and args[0].startswith("-"):
            flag, args = args[0], args[1:]
            if flag in ("-R", "--repo", "--hostname") and args:
                args = args[1:]
        if not args or args[0] != "api":
            continue
        args = args[1:]
        method, fields, endpoint, i = None, False, None, 0
        while i < len(args):
            arg = args[i]
            if arg in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"):
                if i + 1 >= len(args):
                    return False
                i += 1
                if arg in ("-X", "--method"):
                    method = args[i].upper()
                else:
                    fields = True
            elif arg.startswith("--method="):
                method = arg.split("=", 1)[1].upper()
            elif arg.startswith("-X"):
                method = arg[2:].upper()
            elif arg.startswith(("--field=", "--raw-field=", "--input=", "-f", "-F")):
                fields = True
            elif arg in ("-H", "--header", "--jq", "--template", "--cache"):
                i += 1
            elif not arg.startswith("-") and endpoint is None:
                endpoint = arg
            i += 1
        if method is not None and method not in ("GET", "HEAD"):
            return False
        if fields and method is None:
            if endpoint != "graphql" or re.search(r"\bmutation\b", " ".join(args)):
                return False
    return True

sys.exit(0 if check(sys.stdin.read()) else 2)
'; then
    echo "pre-bash-guard: blocked a GitHub API write or unreadable API command" >&2
    echo "Stop and explain the blocked action. Do not retry or delegate it." >&2
    exit 2
fi

exit 0
