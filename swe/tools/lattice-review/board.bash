# >>> board: start or find this repository's Lattice board (agent-alignment AA-34) >>>
board() {
  local git_dir root port actor pid
  git_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || { echo "board: not inside a git repository" >&2; return 1; }
  root=$(dirname "$git_dir")
  [ -f "$root/.lattice/config.json" ] || { echo "board: no Lattice board in $root" >&2; return 1; }
  read -r port actor < <(/usr/bin/python3 -I -c 'import json, sys; c = json.load(open(sys.argv[1])); print(c.get("dashboard_port", 8799), c.get("default_actor", ""))' "$root/.lattice/config.json") || return 1
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    pid=$(ss -Hltnp "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | head -n 1)
    if [ -n "$pid" ] && tr '\0' '\n' < "/proc/${pid#pid=}/cmdline" 2>/dev/null | grep -qxF -- "$root"; then
      echo "board is already running on port $port: open the link in the terminal where it runs"
      return 0
    fi
    # Something else holds the port: move this board to the first free one.
    port=$(/usr/bin/python3 -I - "$root/.lattice" "$port" <<'PY'
import json, os, socket, sys
lattice, old = sys.argv[1], int(sys.argv[2])

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
    echo "board: that port is in use by something else; this board now uses port $port"
  fi
  LATTICE_ROOT="$root" LATTICE_NO_UPDATE_CHECK=1 /usr/bin/python3 -I \
    "@KIT@/swe/tools/lattice-review/lattice_review.py" \
    --board "$root" --port "$port" --actor "${actor:-human:$USER}" \
    --main "$(git -C "$root" config --get lattice-review.base || echo main)"
}
# <<< board <<<
