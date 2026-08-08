# Isolated FreeCAD GUI launch: THIS repo as the addon, throwaway XDG config.
# `freecad` is pinned onto PATH by the flake wrapper (runtimeInputs), so this is
# hermetic. Edit->test loop = relaunch (addon is a pure import side effect run
# inside one closure with a re-entrancy guard, so there is no in-process reload).
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"
dev="${PIEMENU_DEV:-/tmp/piemenu-dev}"

[ -f "$repo/InitGui.py" ] || {
  echo "pm-launch: no InitGui.py under '$repo' (set PIEMENU_REPO)" >&2
  exit 1
}

# XDG override relocates ALL FreeCAD user state (Mod/config/cache) into scratch,
# leaving ~/.config/FreeCAD and ~/.local/share/FreeCAD untouched. The scratch Mod
# dir is empty, so the real ~/.local/share/.../Mod/PieMenu symlink is NOT seen;
# -M adds the repo as the one and only PieMenu module -> exactly one load.
export XDG_DATA_HOME="$dev/data"
export XDG_CONFIG_HOME="$dev/config"
export XDG_CACHE_HOME="$dev/cache"
mkdir -p "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
export PIEMENU_REPO="$repo"
export PIEMENU_DEV="$dev"

# first launch after a reset: seed the demo pies
grep -q "PieMenu/V2" "$XDG_CONFIG_HOME/FreeCAD/v1-1/user.cfg" 2>/dev/null || \
  freecadcmd "$repo/dev/demo_seed.py"

# open FreeCAD's own PartDesign example (a writable copy in scratch);
# fall back to the generated playground doc if this build lacks it
doc="$dev/docs/PartDesignExample.FCStd"
if [ ! -f "$doc" ]; then
  src="$(dirname "$(dirname "$(readlink -f "$(command -v freecad)")")")"
  src="$src/share/examples/PartDesignExample.FCStd"
  mkdir -p "$dev/docs"
  [ -f "$src" ] && install -m 644 "$src" "$doc"
fi
if [ ! -f "$doc" ]; then
  doc="$dev/docs/PieMenuPlayground.FCStd"
  [ -f "$doc" ] || freecadcmd "$repo/dev/demo_docs.py"
fi

echo "pm-launch: isolated config at $dev  (rm -rf to reset)" >&2
exec freecad -M "$repo" "$doc" "$@"
