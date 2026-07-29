# UI feedback log

Feature requests and corrections raised while reviewing the interactive mockup
(`/tmp/claude-1000/piemenu-c.html`). Everything here is a change to make, not a
change already made — the implemented work is tracked in `PLAN-PROGRESS.md`.

## Open

| # | Request | Notes |
| - | ------- | ----- |
| 1 | Right-click menus everywhere they make sense | Keep headers to the few actions used repeatedly; everything occasional or destructive goes to the context menu. |
| 2 | Rename → right-click only | Drop the header button. |
| 3 | Delete pie → right-click only | Drop the header button. |
| 4 | Duplicate pie → right-click only | Drop the header button. |
| 5 | "Use this pie when no workbench matches" → right-click only | The star. Drop the header button. |
| 6 | Add separator stays a button **and** appears in the right-click menu | Both, not either. |
| 7 | Move up / down stay as buttons | The two that stay. |
| 8 | Qt-style dotted drag handles on list rows | Must read as draggable at a glance, on the left of the row. |
| 9 | Drag handles on **pies** too, not just tools | Missed on the first pass. |
| 10 | Tool picker folded by workbench | Expand a workbench to see its tools, rather than one flat list. |
| 11 | Inner circle drawn in the preview | The QuickMenu button at the centre of the pie. |
| 12 | Toolbars belong to their panel | Mounted in the panel header, so it is obvious which list a button acts on. |
| 14 | A distinct icon per tool | Currently every tool row shows the same dot, so the list reads as undifferentiated. |
| 20 | Replace, not delete-then-add | A filled slot's right-click menu needs **Replace tool…**, so changing what is in a slot is one step rather than clearing it and adding again. |
| 23 | Playground needs a workbench switch | Changing workbench there must resolve which pie opens through the Assignment setting, so the workbench-to-pie mapping can actually be tried. |
| 25 | Arc: free number plus presets, and a facing angle | Arc should be typeable as well as pickable, and needs a direction: a 90° arc must be able to face up, down, left or right rather than always starting from the top. |
| 24 | Selection chips do not belong on the preview | Previewing against a selection is an occasional action, so it goes in the preview's right-click menu rather than sitting permanently across the top of it. |
| 21 | A playground under the dialog | A rudimentary viewport: pick a vertex, edge, face or body on a solid, open the pie, and watch which tool each slot resolves to and what firing it does. |
| 15 | Dragging must be visible on the pie itself | The dragged tool should follow the cursor on the preview and the landing slot should be indicated, rather than only updating on drop. |

## Decisions that change shipped work

| # | Decision | Consequence |
| - | -------- | ----------- |
| 13 | **Per-pie export/import does not make sense — export should be all-or-nothing** | This contradicts plan item F9.2, which is already implemented (commit `bc3df9c`). The per-pie export/import buttons come out of the UI, and the commit should be reverted or the feature dropped before this branch is considered done. |

## Design change — needs a backend change too

**16. Consolidate the eleven shapes into two families, with empty slots.**

Today `Shape` is one of eleven values, each a separate branch in `add_commands`
computing positions inline, and a pie's tools fill those positions in list
order with no way to leave a gap.

- **Circle** subsumes Pie, Concentric, Star, RainbowUp and RainbowDown. They
  differ only in parameters: how many slots per ring, whether there is more than
  one ring, whether alternate slots sit at a different radius, and whether the
  arc is a full circle or a half.
- **Grid** subsumes TableTop, TableDown, TableLeft, TableRight, UpDown and
  LeftRight. They differ only in rows, columns, which side of the centre the
  block sits on, and whether it is split either side.

A pie then has *N slots*, and tools are assigned to the slots you want, leaving
the rest empty. That is a better model than filling positions in list order: it
makes layout an arrangement rather than an ordering, and it is what F7's
snap-to-slot already implies.

**Backend consequences**

- Schema: `Shape` becomes a family plus parameters. Existing values must migrate
  (`Pie` → circle/one ring/full arc, `Star` → circle/staggered, `TableTop` →
  grid anchored above, and so on). One migration, not eleven.
- The per-tool `Slot` attribute added in Part 5 becomes load-bearing rather than
  reserved — it is how a tool knows which slot it occupies.
- `ToolList` stays the membership list; slot assignment is per-tool, so a pie can
  have gaps without needing placeholder entries.
- F6.0 extracted only the table family; this replaces that split with two
  layout functions rather than eleven branches, which is a simplification of
  `add_commands` rather than an addition to it.
- Shortcut codes are positional today, so they need to key off slot order.

Mockup first, then the schema.

**22. Split the trigger into two settings: how the pie opens, and how a tool runs.**

Today `TriggerMode` conflates them — Press and Hover describe how a *tool* is
chosen, while opening is always a single key press. Separating them gives every
useful combination from two short lists:

| Open on | Run on |
| ------- | ------ |
| single press | click |
| double tap | hover for a delay |
| press and hold | release (gesture / marking menu) |
| double tap and hold | |

So "double tap and hold, release to run" is a marking menu that cannot fire by
accident, while "single press, click" is the current default. Press-and-hold
variants close the pie on release unless a tool was chosen, which is what makes
a held trigger feel momentary rather than modal.

Schema: `TriggerMode` becomes `OpenOn` plus `RunOn`, with a migration mapping
`Press` → (single, click), `Hover` → (single, hover), `Gesture` → (hold,
release).

## Design change — pinning, hierarchy and conditional slots

**17. Corner pinning is wrong.** Shared tools were placed in the four corners of
the bounding box because those are empty for the pie shapes. But the cursor is
at the *centre* when a pie opens, so a corner is the furthest reachable point on
the menu — the worst place for the tool you reach for most. Corner anchoring
comes out.

**18. Pin a slot, and let child pies inherit it.** Pinning belongs to a *slot*,
not to a corner: a pinned slot keeps its position and its contents in that pie
**and in every pie descended from it**. That requires pies to form a tree rather
than a flat list, so the pie panel needs parents, children and expand/collapse.
Inheritance flows down the tree, so a tool pinned on a parent sits at the same
slot in each child, at the same distance from the cursor.

**19. A slot resolves against the selection, not to a single command.** One slot
holds several conditional bindings:

- a face is selected → the slot is Pad
- an edge is selected → the same slot is Fillet
- nothing that slot knows about applies → the slot is greyed out
- **more than one applies** → hovering the slot opens a slider to choose between
  the candidates

So a slot is a small ordered set of (condition, command) pairs, and what the user
sees in that position depends on what is selected when the pie opens.

**Backend consequences**

- The per-tool context rule from F3 becomes a *per-binding* rule: it already
  evaluates a six-axis condition, but it currently answers "enable or grey this
  tool", not "which of these tools belongs here".
- `ToolList` cannot express this at all — a slot needs a list of bindings, each
  with its own rule. This lands on top of the slot model from feedback #16.
- Pie parentage is new: an index entry needs a parent, and cycles must be
  rejected.
- `SharedToolList` and the per-tool `Anchor` from F8.c are replaced by a pinned
  flag on a slot, so commit `b619aed` is superseded rather than extended.
- Resolution happens when the pie is built, which is where F3 already evaluates.
  The hover-to-choose slider is new interaction, not just new layout.

## Notes

- Feature requests raised in review get written here as they come up, so they can
  be folded into a plan rather than lost in conversation.
