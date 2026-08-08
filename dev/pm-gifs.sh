# Render the demo GIF suite: an offscreen FreeCAD runs dev/gif_scenes.py
# against a throwaway profile and writes looping GIFs to docs/gifs/.
# Same isolation story as pm-snap: own sub-scratch, theme-free, seeded.
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"
dev="${PIEMENU_DEV:-/tmp/piemenu-dev}/gifs"
rm -rf "$dev"

[ -f "$repo/InitGui.py" ] || {
  echo "pm-gifs: no InitGui.py under '$repo' (set PIEMENU_REPO)" >&2
  exit 1
}

export XDG_DATA_HOME="$dev/data"
export XDG_CONFIG_HOME="$dev/config"
export XDG_CACHE_HOME="$dev/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
export QT_QPA_PLATFORM=offscreen
export PIEMENU_REPO="$repo"

freecadcmd "$repo/dev/demo_seed.py"

log="$dev/gifs.log"
timeout --kill-after=10 240 freecad -M "$repo" "$repo/dev/gif_scenes.py" \
  >"$log" 2>&1 || true
grep "^GIF" "$log" || true
if grep -q "GIFS-DONE" "$log"; then
  echo "pm-gifs: GIFs in $repo/docs/gifs"
else
  echo "pm-gifs: FAIL — log tail:" >&2
  tail -25 "$log" >&2
  exit 1
fi
