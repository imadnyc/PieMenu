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

## Notes

- Feature requests raised in review get written here as they come up, so they can
  be folded into a plan rather than lost in conversation.
