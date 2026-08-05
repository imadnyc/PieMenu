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

echo "pm-launch: isolated config at $dev  (rm -rf to reset)" >&2
exec freecad -M "$repo" "$@"
