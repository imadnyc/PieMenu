# Building the v2 design into the addon

The mockup (`mockups/preferences2.html`) settled the design; `UI-FEEDBACK.md`
records every decision and its rationale. This file maps those decisions onto
the real addon as a sequence of small, individually reviewable commits.

**Strategy: v2 lands beside v1.** The new schema lives under its own parameter
subtree (`User parameter:BaseApp/PieMenu/V2`) and new code lives in new
modules, so the addon keeps working on the v1 path at every commit. Only when
the v2 runtime is complete does the entry point flip over, and only after that
do the v1 paths get deleted. FreeCAD stays launchable throughout.

## The settled model (one paragraph)

Pies are a **flat set**; a pie is an ordinary **command** (`PieMenu_<name>`),
so a slot can open a pie the same way it runs a tool. A **slot** is an ordered
list of *(rule → command)* bindings — first match wins, several matches offer
the chooser. A **rule** is a sparse six-axis condition (`Face ≥ 2`,
`Face ≥ 1 · Edge ≥ 1`) — exactly what `matchesContext` already evaluates,
minus the dense-storage requirement. **Shortcuts** are workbench-scoped:
`binds[scope][key] = pie`, where the `Any` scope is the base a workbench
overrides. Editors show the **union** (tables); only live use **resolves**.

## Schema v2 (`…/PieMenu/V2`)

```
V2/Pies/<name>/          Family, Icon, Default(Bool),
                         Slots, PerRing, Radius, Arc, ArcFace,
                         Stagger(Bool), StaggerBy,
                         Cols, Rows, Anchors("Top,Bottom,Right"),
                         Button, Spacing,
                         OpenOn, RunOn, Delay, ShowNames(Bool)
V2/Pies/<name>/Slots/S<i>/B<j>/   Command, Rule("Face>=1;Edge>=1", ""=always)
V2/Shortcuts/<scope>/    one String param per key: value = pie name
                         (<scope> = "Any" or a workbench name)
V2/SchemaVersion         2 once migrated
```

Behaviour toggles reuse the existing global params the runtime already reads
(`ShowQuickMenu`, `GlobalKeyToggle`, `RightClickTrigger`, `DelayRightClick`).
Global context (legacy auto-open-on-selection) stays a placeholder — open
question recorded in UI-FEEDBACK.

## Phases

Each phase is one or a few commits; each names its verification. Headless =
`nix run .#smoke` (freecadcmd, offscreen, isolated scratch config). GUI =
`nix run .#watch` (isolated live FreeCAD, restart-on-save).

- **A — model** (`piemenu/model.py` + `dev/test_model.py`): rule codec,
  sparse matcher, Pie dataclass, slot bindings, positions() (circle with
  stagger-by, multi-anchor grid), shortcut resolution, pie-liveness with
  cycle-safe recursion, ParamGet round-trip. Dormant: nothing imports it at
  startup yet. *Verify: headless tests.*
- **B — migration v1 → v2**: read `Index/<i>` pies, map the eleven shapes to
  the two families (UI-FEEDBACK #16 table), ToolList order → slots, per-tool
  context params → sparse rules, legacy global/per-pie shortcuts → scoped
  binds. Idempotent, additive, `V2/SchemaVersion=2`. Not yet called at
  startup. *Verify: headless — seed a legacy tree, migrate, assert.*
- **C — v2 runtime**: pie rendering reads v2 (model.positions), shortcut
  dispatch resolves key×workbench (drops the four fixed global slots),
  slot resolution + chooser against live selection counts, doors open pies
  at the cursor (NestedPieMenu already exists — keep), behaviour params
  honoured. Startup runs migration, then the flip. *Verify: headless load +
  GUI checklist mirroring the mockup playground (key 1 face/edge cases,
  descent Main→Modelling→Patterns, toggle, RMB-hold).*
- **D — dialog**: rebuild preferences to the mockup: flat pie list (icons,
  default/unused tags), clean preview with markers + cross-highlight, Slots
  table (union, rules edited in place), settings knobs (sliders, ring
  readout, anchor cross), searchable picker with recap + live pie group,
  shortcuts table (pinned key/Any columns, recordable keycaps, row delete),
  hover help. One panel per commit. *Verify: GUI, per panel.*
- **E — cleanup**: unwind the superseded shipped work — `bc3df9c` (per-pie
  export, #13), `b619aed` (corner pinning, superseded by deferred #17/18),
  `2b75adc` (table-family split, superseded by #16), `cb443f3` (single
  TriggerMode, superseded by #22) — then delete the v1 dialog/runtime paths
  and dead params. *Verify: headless + full GUI regression sweep.*
- **F — deferred, explicitly out**: pinning (#17/#18) revisited only after
  the above; Global context semantics.

## Rules of the road

- Every commit stands alone, builds, and keeps `nix run .#smoke` green.
- No commit mixes phases. Dialog commits are one panel each.
- The mockup is the spec of record; disagreements get resolved in
  UI-FEEDBACK.md first, code second.

## Status — built, verified, ready for review

All phases through the flip are done on `v2-build`:

| Phase | Commit | Verified by |
| ----- | ------ | ----------- |
| Plan | `c54aad6` | — |
| A model | `c6d5d9f` | `dev/test_model.py` (8 groups) |
| B migration | `8a2e2df` | `dev/test_migrate.py` (legacy tree + fresh install) |
| C runtime | `e1691e0` | `dev/test_runtime.py` (widget, chooser, doors, dispatch) |
| D dialog | `5616dc1` | `dev/test_dialog.py` (panels, tables, picker, rules) |
| Flip + E | `35375ab` | `dev/smoke_freecad.py` (v2 startup over a legacy tree) |
| E2E | `d927ae5` | `dev/test_gui.py` in a real offscreen GUI |

`InitGui.py`: 7569 lines → 75. The package: model 356, migrate 208, runtime
582, dialog 1329, constants 50, resources 26.

**Run everything:** `nix run .#smoke` (5 headless suites, isolated config)
and `nix run .#e2e` (real GUI, offscreen). Interactive: `nix run .#watch`
(edit → save → FreeCAD relaunches, isolated), or `nix run .#launch` once.

**Dropped with the legacy body** (deliberate, revisit on demand): the
theme/stylesheet system, toolbar import, per-pie export/import (whole-tree
export lives in the behaviour dialog), corner pinning (deferred #17/#18),
the legacy auto-open context observer (the Global-context open question),
and the spinbox display option. The mockup remains the spec of record; the
mockups/ pages document intent for anything not yet obvious from the UI.

## Gesture bindings (2026-08-06)

A binding is now key x scope x **gesture** -> pie: `tap`, `double`
(double-press) and `hold` (press-and-hold), stored as
`Shortcuts/<scope>/<key>` (bare = tap, pre-gesture configs read unchanged)
or `Shortcuts/<scope>/<key> <gesture>`. Each gesture inherits through the
Any scope independently; `run_on` stays on the pie. The pie's `open_on`
field is retired from the UI and the dispatcher (still stored/loaded for
compatibility). Dispatcher semantics: tap opens on press (toggle applies);
a second press within 350ms swaps to the double pie; hold opens for
gesturing, and a release under 250ms falls back to the tap binding when
one exists. The shortcuts table stacks one glyph-prefixed line per gesture
(`·` `··` `—`), inherited lines shown as `↳ pie` in dim italics, with a
legend underneath.
