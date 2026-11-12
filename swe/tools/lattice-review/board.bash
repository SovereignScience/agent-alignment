# >>> board: start or find this repository's Lattice board (agent-alignment AA-34) >>>
board() {
  local git_dir root port
  git_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || { echo "board: not inside a git repository" >&2; return 1; }
  root=$(dirname "$git_dir")
  [ -f "$root/.lattice/config.json" ] || { echo "board: no Lattice board in $root" >&2; return 1; }
  read -r port actor < <(/usr/bin/python3 -I -c 'import json, sys; c = json.load(open(sys.argv[1])); print(c.get("dashboard_port", 8799), c.get("default_actor", ""))' "$root/.lattice/config.json") || return 1
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "board is already running: http://127.0.0.1:$port"
    return 0
  fi
  LATTICE_ROOT="$root" LATTICE_NO_UPDATE_CHECK=1 /usr/bin/python3 -I \
    "@KIT@/swe/tools/lattice-review/lattice_review.py" \
    --board "$root" --port "$port" --actor "${actor:-human:$USER}" \
    --main "$(git -C "$root" config --get lattice-review.base || echo main)"
}
# <<< board <<<
