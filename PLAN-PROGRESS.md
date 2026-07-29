# Plan progress

Tracks `thisihavemorereplicatedmochi.md`. Tags mark phase boundaries:
`git log phase-0-complete..phase-1-decoupling-complete`.

## Phase 0 — quick wins  (tag: `phase-0-complete`)

| item | commit | note |
| ---- | ------ | ---- |
| F5.1 preview resizeEvent | `09ae111` | |
| F7.0 drag-to-reorder tool list | `3d79ac9` | not "nearly free": QTableWidget InternalMove moves cells, so the drop is fully overridden |
| F1.b CurrentPie / ActivePie split | `9ee4b54` | also clears ActivePie when a default is set, else the default still loses |
| F1.a relabel default checkbox | `c5c5e49` | |
| F8.b PieMenus in the tool picker | `c0911fa` | also fixes NestedPieMenu discarding its iconPath |
| F4.1 regroup Global settings tab | `77b1916` | found 2 more mistagged contexts than the plan listed: the Assign buttons were swapped |
| F9 try existing export/import | — | **user action, not code** |

## Phase 1 — decoupling, Part 3  (tag: `phase-1-decoupling-complete`)

| item | commit | note |
| ---- | ------ | ---- |
| 1 memoize param handles | `c1ffb87` | |
| 2 reorder eventFilter | `46c71f5` | |
| F11 Wayland pointer cache | `074215b` | rides along with 2, as planned |
| (extra) backfill DelayRightClick | `d444e8d` | not in the plan; commit 4 regresses without it |
| 3 right-click settings from params | `0596b3a` | |
| 4 GlobalKeyToggle from params | `f009f08` | |
| 5 ShowQuickMenu from params | `297b679` | |
| 6 isPreviewMode() | `6dd973a` | |
| 7a getShape split | `f06a995` | |
| 8 tool-list key filter | `84c8165` | installed on buttonListWidget, not the dialog |
| 9 ensureDefaultPieGroup | `2e2adbc` | |
| 7b Wire E | `f536f17` | **behaviour change**, as the plan flags |

After 7b, nothing reachable from the hotkey reads a preferences-dialog widget.

## Not started

- **Phase 1 remainder**: lazy dialog construction, F11.2, F4.2, F4.3
- **Phase 2**: Part 5 tool model + the one migration, F3.1, F3, F8.c, F2, F9.2, F6.0
- **Phase 3**: F6, F7, F10a, F10b, F4.4

### Next step, and why it stopped here

Lazy dialog construction is the next item. Measured: the block is **1,092 lines
binding 214 names, 68 of which are referenced from outside it** by callbacks
defined earlier in the closure. Making it lazy therefore needs those 68
pre-declared and re-bound with `nonlocal`, or the callbacks stop resolving.
That is the largest structural change in the plan and the hardest to isolate if
it breaks -- so it waits until the 17 commits above are confirmed in a running
FreeCAD, per Part 6.
