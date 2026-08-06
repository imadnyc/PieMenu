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

# freecadcmd exits 0 even when the script raises, so trusting exit codes makes
# every failure silent -- each file must print its sentinel or the suite fails
run() {
  out=$(freecadcmd -u "$XDG_CONFIG_HOME/$2-user.cfg" "$repo/dev/$1" 2>&1)
  printf '%s\n' "$out"
  printf '%s' "$out" | grep -q "$3" || {
    echo "pm-smoke: FAIL — $1 never printed $3" >&2
    exit 1
  }
}
run smoke_freecad.py smoke SMOKE-PASS
run test_model.py model MODEL-TESTS-PASS
run test_migrate.py migrate MIGRATE-TESTS-PASS
run test_runtime.py runtime RUNTIME-TESTS-PASS
run test_dialog.py dialog DIALOG-TESTS-PASS
echo "pm-smoke: ALL PASS"
