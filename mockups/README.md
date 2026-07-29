# Mockups — reference only, not for upstream

Interactive prototypes used to design the preferences dialog. They are **not**
part of the addon and must not be included in an upstream pull request: this
directory exists so the design work is kept alongside the code it describes,
and so the decisions behind it can be re-read later.

    python3 mockups/build.py && xdg-open mockups/preferences.html

`build.py` inlines the addon's own SVGs from `Resources/icons` as markup —
a browser will not render them from an `<img src="data:...">`, which is why an
earlier attempt showed nothing. Those 23 icons are interface chrome: add,
remove, up, down, rename, copy, separator. Per-command icons such as Pad or
Fillet live in FreeCAD's compiled resources rather than in this repository, so
the mockup draws stand-ins for those.

`preferences.html` is generated; edit `preferences.template.html`.

## What it demonstrates

- **The pie is the editor.** There is no tool list. Double-click a slot to pick
  a tool from the global list folded by workbench; right-click a slot for its
  options; drag a slot to move a tool between positions.
- **Slots exist whether or not they are filled**, so a layout is an arrangement
  rather than an ordering.
- **Two shape families instead of eleven** — see feedback #16 in
  `../UI-FEEDBACK.md`. `circle` covers Pie, Concentric, Star and both Rainbows;
  `grid` covers the four Tables plus UpDown and LeftRight.
- The features added in this branch that previously had **no interface at all**:
  per-tool context rules, shared/pinned tools, layout regions and shortcut slots.

Outstanding feedback is tracked in `../UI-FEEDBACK.md`.
