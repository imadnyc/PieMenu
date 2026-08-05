# End-to-end: a real (offscreen) FreeCAD GUI runs the flipped addon from this
# repo against a pristine scratch config, and dev/test_gui.py drives it --
# startup, migration, command registration, the pie widget, key dispatch and
# the preferences dialog. The log decides the verdict.
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"
dev="${PIEMENU_DEV:-/tmp/piemenu-dev}/e2e"

[ -f "$repo/InitGui.py" ] || {
  echo "pm-e2e: no InitGui.py under '$repo' (set PIEMENU_REPO)" >&2
  exit 1
}

rm -rf "$dev"
export XDG_DATA_HOME="$dev/data"
export XDG_CONFIG_HOME="$dev/config"
export XDG_CACHE_HOME="$dev/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
export QT_QPA_PLATFORM=offscreen

log="$dev/e2e.log"
timeout --kill-after=10 120 freecad -M "$repo" "$repo/dev/test_gui.py" \
  >"$log" 2>&1 || true

grep "^E2E" "$log" || true
if grep -q "E2E-PASS" "$log" && ! grep -q "E2E-FAIL" "$log"; then
  echo "pm-e2e: PASS"
else
  echo "pm-e2e: FAIL — log tail:" >&2
  tail -30 "$log" >&2
  exit 1
fi
