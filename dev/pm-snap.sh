# Photograph the addon's widgets: an offscreen FreeCAD runs dev/snap.py
# against the scratch profile and saves PNGs to /tmp/piemenu-snaps for the
# styling loop. Seeds the demo config first if the scratch is empty.
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"
# own sub-scratch: the themed main profile hangs the OFFSCREEN platform (the
# Theme/StyleSheet load), so captures run against a theme-free config
dev="${PIEMENU_DEV:-/tmp/piemenu-dev}/snap"

[ -f "$repo/InitGui.py" ] || {
  echo "pm-snap: no InitGui.py under '$repo' (set PIEMENU_REPO)" >&2
  exit 1
}

export XDG_DATA_HOME="$dev/data"
export XDG_CONFIG_HOME="$dev/config"
export XDG_CACHE_HOME="$dev/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
export QT_QPA_PLATFORM=offscreen
export PIEMENU_REPO="$repo"

grep -q "PieMenu/V2" "$XDG_CONFIG_HOME/FreeCAD/v1-1/user.cfg" 2>/dev/null || \
  freecadcmd "$repo/dev/demo_seed.py"

log="$dev/snap.log"
timeout --kill-after=10 120 freecad -M "$repo" "$repo/dev/snap.py" \
  >"$log" 2>&1 || true
grep "^SNAP" "$log" || true
if grep -q "SNAP-DONE" "$log"; then
  echo "pm-snap: PNGs in /tmp/piemenu-snaps"
else
  echo "pm-snap: FAIL — log tail:" >&2
  tail -20 "$log" >&2
  exit 1
fi
