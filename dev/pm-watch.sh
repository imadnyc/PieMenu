# The fast loop: watch every .py in the repo and relaunch FreeCAD on any change.
# entr -r keeps ONE FreeCAD child alive and restarts it when a watched file is
# written; -d makes entr exit if a new file appears in a watched dir, so the
# while-loop re-globs and picks it up. Save a file -> FreeCAD restarts with the
# new code. (Restart, not hot reload: the addon's one-closure design defeats
# in-process reload -- see dev/README.md.) pm-launch does the isolation + -M load.
repo="${PIEMENU_REPO:-/home/dre/Projects/PieMenu}"

[ -f "$repo/InitGui.py" ] || {
  echo "pm-watch: no InitGui.py under '$repo' (set PIEMENU_REPO)" >&2
  exit 1
}

echo "pm-watch: watching *.py under $repo -- save to relaunch, Ctrl-C to stop" >&2
# Ctrl-C must stop the whole thing, not just the current entr (else the loop
# relaunches FreeCAD forever). entr exits 0 on -d (new file appeared) -> re-glob;
# on SIGINT the trap fires and we exit.
trap 'echo; exit 0' INT
while true; do
  # -n: don't read the tty (works when launched without a controlling terminal,
  # e.g. from a task runner); -r: keep one FreeCAD alive, restart it on change;
  # -d: exit if a new file appears in a watched dir so the loop re-globs.
  find "$repo" -name '*.py' -not -path '*/dev/*' -not -path '*/.git/*' \
    | entr -nrd pm-launch
done
