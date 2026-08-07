# PieMenu v2

Marking-menu style pie menus for FreeCAD — press a key, flick at a tool,
release. A ground-up rewrite of the PieMenu addon (forked from
[Grubuntu/PieMenu](https://github.com/Grubuntu/PieMenu)) around three ideas:

- **The gesture belongs to the binding.** One key can carry four pies per
  workbench: `·` press, `··` double-press, `—` press-and-hold and `··—`
  double-press-and-hold, each resolving independently through an
  *Any-workbench* fallback (a workbench binding always beats the base).
- **Conditions belong to slots.** A slot holds an ordered list of
  *(rule → command)* bindings over six selection axes (Vertex, Edge, Face,
  Object, Axis, Plane). First match wins; several matches offer a small
  chooser, and the chooser remembers your pick as the slot's new face.
- **A pie is just a command.** Every pie registers as `PieMenu_<name>`, so
  slots can open other pies ("doors") — conditionally, too. Dwelling on a
  door glides straight into it at the cursor; the centre grows a back
  button.

## What it does

- **Gesture pies** (*Run on: release*): press opens, an arrow follows your
  aim, release fires — releasing from the centre dead-zone just closes.
  Click pies stay open for the mouse and toggle on re-press.
- **Workbench-scoped shortcuts** in one table: keys × workbenches, gesture
  lines stacked per cell, inherited bindings shown dim-italic with `↳`,
  the current workbench bold and tinted.
- **The Smart pie** — bind it anywhere (F9 in the starter set) and it
  rebuilds itself at every open from your most-used tools in the current
  workbench. Usage counts decay over time, so it follows what you use
  *now*. Its layout and behaviour are editable like any pie; only its
  contents are computed. A Stats panel shows the numbers.
- **Layouts**: circles with multiple rings (uniform, auto-fit by
  circumference, or custom counts per ring), or grids anchored to any
  sides of the cursor with independent per-block offsets.
- **Editing**: live preview with a marker legend, context-clash linting
  (an always-on tool mixed into a conditional slot is flagged), drag to
  swap slots, right-click a slot in a *live* pie to replace/re-rule/
  relabel it, per-binding display labels, digit keys 1–9 fire slots,
  Shift = sticky fire (chain tools without reopening), wheel zooms an
  open pie.
- **Colours**: accent, outline, fill and arrow are each themeable per
  config (and accent per pie); everything else follows the FreeCAD theme.
- **More**: macros as slot targets, single-pie export/import as JSON,
  new-pie-from-a-toolbar, starter templates, optional auto-open when the
  selection matches a conditional slot, and structural edits stash
  trimmed slots so a mistyped count loses nothing.

## Install

```sh
git clone https://github.com/imadnyc/PieMenu ~/PieMenu
ln -s ~/PieMenu ~/.local/share/FreeCAD/v1-1/Mod/PieMenu
```

Restart FreeCAD. Existing v1 PieMenu configurations migrate automatically
and non-destructively (the v1 data is left in place).

For a ready-made starter set — eight pies on F3–F9, including the Smart
pie — merge it into your profile (nothing you already have is touched):

```sh
freecadcmd ~/PieMenu/dev/install_seed.py
```

Preferences live under **Tools ▸ Accessories ▸ PieMenu preferences…**

## The starter keys

| Key | Anywhere | PartDesign | Sketcher |
|-----|----------|------------|----------|
| F3 `·` | Main | *(inherited)* | *(inherited)* |
| F3 `—` | | Modelling (gesture) | Sketching (gesture) |
| F3 `··—` | | Patterns (gesture) | |
| F4 `·` / `··` | Modelling / Patterns | | |
| F6 `·` | View | | |
| F7 `·` / `—` | Booleans | | Constraints (gesture) |
| F8 `·` | Datums | | |
| F9 `·` | Smart — your most used | | |

## Development

Hermetic dev environment via Nix (FreeCAD 1.1.1 pinned); everything runs
against a throwaway profile in `/tmp/piemenu-dev` — your real
configuration is never touched.

```sh
nix run .#launch   # isolated FreeCAD with this repo as the addon
nix run .#watch    # relaunch on every save
nix run .#smoke    # headless test suite (freecadcmd, offscreen)
nix run .#e2e      # end-to-end inside a real offscreen GUI
nix run .#snap     # photograph widgets/dialogs to /tmp/piemenu-snaps
```

`IMPLEMENTATION.md` is the build log and schema reference;
`UI-FEEDBACK.md` records the design decisions; `mockups/` holds the
interactive HTML mockups the design was iterated in.

## Credits and licence

Based on PieMenu by microelly (2015), looo, triplus, mdkus, Grubuntu,
Pgilfernandez, hasecilu and Ben-PH. LGPL-2.1-or-later, like the original.
