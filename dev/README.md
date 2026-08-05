# PieMenu dev environment

A hermetic nix flake for iterating on the addon without touching your real FreeCAD config.

```sh
nix develop        # shell: freecad + python + ruff, and pm-watch/pm-launch/pm-smoke
nix run .#watch    # THE FAST LOOP: save any .py -> FreeCAD relaunches with new code
nix run .#launch   # one isolated FreeCAD GUI with this repo as the addon
nix run .#smoke    # headless: assert the addon loads and the migration runs
```

## The fast loop

`pm-watch` (`nix run .#watch`, the default app) watches every `.py` in the repo with
`entr` and keeps one FreeCAD alive, restarting it the instant you save. Edit → save →
FreeCAD is back with your change. It's a restart, not a hot reload: the addon runs
entirely inside one closure at import behind a re-entrancy guard, so re-importing in place
leaves edits inert and double-installs the app-wide event filter — a fresh process is the
only thing that cleanly re-runs the wiring. `pm-watch` just makes that fresh process
automatic and cheap (single-Mod scratch profile).

## How it works

- **FreeCAD is hermetic** — built from the pinned nixpkgs rev (vtk + freecad from source
  once, then cached and pushed to the moss cache). `freecad`/`freecadcmd` inside the shell
  and wrappers resolve to that pin, not your ambient profile.
- **Isolation:** the wrappers set `XDG_{DATA,CONFIG,CACHE}_HOME` to a scratch tree
  (`$PIEMENU_DEV`, default `/tmp/piemenu-dev`), so all FreeCAD user state — Mod dir,
  `user.cfg`, cache — lands there. Your real `~/.config/FreeCAD` and
  `~/.local/share/FreeCAD` are never written. `rm -rf /tmp/piemenu-dev` resets to pristine.
- **The repo loads via `freecad -M <repo>`** (its `package.xml` marks the root as the
  addon), so exactly one PieMenu loads, from your working tree.

## One-time cleanup you may want

`~/.local/share/FreeCAD/v1-1/Mod/PieMenu` is a symlink to this repo in your **real**
config, so plain `freecad` (no wrapper) still loads the dev code into your real profile.
Remove it if you want the addon to load *only* in the isolated dev instance:

```sh
rm ~/.local/share/FreeCAD/v1-1/Mod/PieMenu
```
