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
