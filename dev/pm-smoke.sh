# Headless smoke test: load the addon end-to-end under freecadcmd (offscreen),
# assert the param-tree migration + IndexList dedupe. Prints SMOKE-PASS on success.
# Belt-and-suspenders isolation: -u pins user.cfg into scratch (freecadcmd otherwise
# PERSISTS param writes to the REAL user.cfg on exit) AND XDG relocates data/cache.
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"
dev="${PIEMENU_DEV:-/tmp/piemenu-dev}"

command -v freecadcmd >/dev/null 2>&1 || {
  echo "pm-smoke: 'freecadcmd' not on PATH" >&2
  exit 1
}

export PIEMENU_REPO="$repo"
export QT_QPA_PLATFORM=offscreen
export XDG_DATA_HOME="$dev/data"
export XDG_CONFIG_HOME="$dev/config"
export XDG_CACHE_HOME="$dev/cache"
mkdir -p "$XDG_CONFIG_HOME"

freecadcmd -u "$XDG_CONFIG_HOME/smoke-user.cfg" "$repo/dev/smoke_freecad.py"
freecadcmd -u "$XDG_CONFIG_HOME/model-user.cfg" "$repo/dev/test_model.py"
exec freecadcmd -u "$XDG_CONFIG_HOME/migrate-user.cfg" "$repo/dev/test_migrate.py"
