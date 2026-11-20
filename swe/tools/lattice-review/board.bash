# >>> board: start or find this repository's Lattice board (agent-alignment AA-34) >>>
board() {
  local git_dir root port actor new
  git_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || { echo "board: not inside a git repository" >&2; return 1; }
  root=$(dirname "$git_dir")
  [ -f "$root/.lattice/config.json" ] || { echo "board: no Lattice board in $root" >&2; return 1; }
  read -r port actor < <(/usr/bin/python3 -I -c 'import json, sys; c = json.load(open(sys.argv[1])); print(c.get("dashboard_port", 8799), c.get("default_actor", ""))' "$root/.lattice/config.json") || return 1
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    # Something holds the port. Leave this board's own server running,
    # however it was started; otherwise move this board to a free port.
    new=$(/usr/bin/python3 -I - "$root" "$port" <<'PY'
import argparse, json, os, re, socket, subprocess, sys
root, old = sys.argv[1], int(sys.argv[2])
lattice = os.path.join(root, ".lattice")

def served_board(port):
    """The board directory of the lattice_review.py listening on port, else None."""
    listing = subprocess.run(["ss", "-Hltnp", "sport = :%d" % port], capture_output=True, text=True, check=True).stdout
    pid = re.search(r"pid=(\d+)", listing)
    if pid is None:
        return None
    with open("/proc/%s/cmdline" % pid[1], "rb") as f:
        argv = [os.fsdecode(arg) for arg in f.read().split(b"\0")]
    script = next((i for i, arg in enumerate(argv) if arg.endswith("lattice_review.py")), None)
    if script is None:
        return None
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--board", default=".")
    board = parser.parse_known_args(argv[script + 1:])[0].board
    return os.path.realpath(os.path.join(os.readlink("/proc/%s/cwd" % pid[1]), board))

if served_board(old) == os.path.realpath(root):
    print("running")
    sys.exit()

def free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0

new = next((p for p in range(8803, 8900) if free(p)), None)
if new is None:
    sys.exit("board: port %d is in use by something else and no port from 8803 to 8899 is free" % old)
config = os.path.join(lattice, "config.json")
with open(config) as f:
    data = json.load(f)
data["dashboard_port"] = new
with open(config + ".new", "w") as out:
    json.dump(data, out, indent=2, sort_keys=True)
    out.write("\n")
os.replace(config + ".new", config)
context = os.path.join(lattice, "context.md")
if os.path.exists(context):
    with open(context) as f:
        text = f.read()
    with open(context + ".new", "w") as out:
        out.write(text.replace("127.0.0.1:%d" % old, "127.0.0.1:%d" % new))
    os.replace(context + ".new", context)
print(new)
PY
    ) || return 1
    if [ "$new" = running ]; then
      echo "board is already running on port $port: open the link in the terminal where it runs"
      return 0
    fi
    echo "board: that port is in use by something else; this board now uses port $new"
    port=$new
  fi
  LATTICE_ROOT="$root" LATTICE_NO_UPDATE_CHECK=1 /usr/bin/python3 -I \
    "@KIT@/swe/tools/lattice-review/lattice_review.py" \
    --board "$root" --port "$port" --actor "${actor:-human:$USER}" \
    --main "$(git -C "$root" config --get lattice-review.base || echo main)"
}
# <<< board <<<
