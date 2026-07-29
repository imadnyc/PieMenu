# Plan progress — complete

Implements `thisihavemorereplicatedmochi.md`. Tags mark phase boundaries:

```
git log phase-0-complete                                  # Phase 0
git log phase-0-complete..phase-1-complete                # Phase 1
git log phase-1-complete..phase-2-complete                # Phase 2
git log phase-2-complete..phase-3-complete                # Phase 3
```

## Phase 0 — quick wins  (`phase-0-complete`)

| item | note |
| ---- | ---- |
| F5.1 preview resizeEvent | |
| F7.0 drag-to-reorder tool list | not "nearly free": QTableWidget InternalMove moves cells, so the drop is fully overridden |
| F1.b CurrentPie / ActivePie split | also clears ActivePie when a default is set, or the default still loses |
| F1.a relabel default checkbox | |
| F8.b PieMenus in the tool picker | also fixes NestedPieMenu discarding its iconPath |
| F4.1 regroup Global settings tab | found 2 mistagged contexts beyond the plan's 4: the Assign buttons were swapped |
| F9 try existing export/import | **user action — not code** |

## Phase 1 — decoupling  (`phase-1-complete`)

Part 3 commits 1-9, plus **7b (Wire E)**, F11, lazy dialog construction, F11.2,
F4.2, F4.3. Extra commit not in the plan: backfill `DelayRightClick`, without
which commit 4 regresses.

After 7b, nothing reachable from the hotkey reads a preferences-dialog widget,
which is what allows the dialog to be built on first use rather than at startup
(~200 widget constructions off every FreeCAD launch).

## Phase 2 — foundations  (`phase-2-complete`)

| item | note |
| ---- | ---- |
| Part 5 per-tool model | one additive migration, guarded by `SchemaVersion` |
| (extra) IndexList dedupe | the real config had indices 1 and 2 listed twice |
| F3.1 extract `matchesContext()` | |
| F3 per-tool context | disables the **button**, never the shared action |
| F8.c shared/pinned tools | corners are already empty, so this needed no F6 |
| F2 multi-slot keyboard binds | slot 1 keeps `GlobalShortcutKey` verbatim |
| F9.2 per-pie export/import | after the tool model, so attributes travel |
| F6.0 extract shape dispatch | table family only — see below |

## Phase 3 — layout  (`phase-3-complete`)

| item | note |
| ---- | ---- |
| F6 composite layouts | extra regions with their own shape/radius/spacing |
| F7 snap-to-slot | stores `(slot)`, not pixels, so layouts survive DPI changes |
| F10a Gesture trigger | needed F11's pointer cache; nearest-button fallback |
| F10b origin→cursor line | first `paintEvent` in the addon |
| F4.4 splitter + ToolBars | preview takes the slack |

## Known limits

- **F6.0 is partial.** Pie and LeftRight interleave geometry with per-button
  styling and text measurement; Concentric and Star grow `self.radius` as the
  loop runs, so button N depends on having walked 1..N-1. Only the table family
  is callable standalone, so an extra region asking for a pie-family shape falls
  back to `TableRight`.
- **No GUI verification.** Everything is `py_compile` plus semantic probes against
  the running FreeCAD's Qt. Nothing has been exercised in a rebuilt session.
- Part 7 backlog untouched by design (`package.xml` license path, unguarded
  `int(fc_version[…])`, `showPiemenuPreview` duplication, bare `except: None`).
