# Feature inventory

One row per feature, so any of them can be found — and ripped out — fast.
"Remove" names the anchors to delete; tests that cover the feature will
fail and point at the rest. Params live under
`User parameter:BaseApp/PieMenu`.

## Triggers and gestures

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Per-workbench shortcuts | a key means different pies per workbench, `Any` is the fallback | `model.resolve_key`, `model.scope_chain` | core, keep |
| SketchEdit scope | editing a sketch is its own scope, falls back through Sketcher | `model.SKETCH_EDIT_SCOPE`, `runtime.workbench_scope`, `dialog.workbench_scopes` | drop the scope from `scope_chain` + `workbench_scopes` |
| Four gestures per key | tap / double / hold / double-hold, quick-vs-held state machine | `runtime.Dispatcher` (`DOUBLE_MS`, `DEFER_MS`) | core, keep |
| Move-opens-sooner | mouse movement during an ambiguous press opens the hold pie at once | `Dispatcher.eventFilter` MouseMove branch | delete that branch |
| Mouse thumb buttons | Mouse4/Mouse5 bind like keys, all gestures | `runtime.MOUSE_KEYS`, mouse branches in `Dispatcher.eventFilter`, `dialog._MouseCatch` | delete those three |
| Right-click trigger | long right-click opens the resolved pie | `Dispatcher._arm_rclick`, `RightClickTrigger` param | delete methods + param |
| Angular aim | circle pies read the gesture as a direction: radius picks the ring, angle the slot; dead/empty sectors are no-ops; ~5° boundary stickiness | `PieWidget._angular_slot`, `_sectors` in `build` | delete both; the Euclidean fallback in `nearest_slot` takes over |
| Aim feedback | the aimed slot wears an accent ring and the centre names what release will do ("Cancel" in the dead zone) | `PieWidget._set_aim`, `aimed` rule in `build`, `aimname` property in `_decorate` | delete those three |
| Flick-overshoot lock | on grids and arc pies, releasing where nothing resolves fires the slot crossed <150 ms ago | `PieWidget._crossed` in `mouseMoveEvent` + `commit_gesture` | delete both `_crossed` blocks |

## Slots and rules

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Selection conditions | per-binding rules over six axes, first match wins | `model.match_rule`, `decode_rule` | core, keep |
| Chooser | overloaded slot pops flavours, remembers last pick | `runtime._chooser_widget`, `last_used` | core-ish |
| Doors | slots opening other pies in place, back button | `model.PIE_PREFIX`, `PieWidget.activate/back` | core, keep |
| Hover doors + dwell ring | dwelling on a door descends mid-gesture | `_HoverFire` install in `_slot_button`, `door_hover` field | uncheck per pie, or delete the elif |
| Instant doors | per-pie: descend on enter, no dwell | `door_instant` field, delay choice in `_slot_button`, checkbox in dialog settings | delete field + checkbox |
| Macros as slots | `Macro:file.FCMacro` targets | `model.MACRO_PREFIX`, branch in `Runtime.fire`, picker group | delete prefix branches |
| Workbench slots | a workbench as a slot activates it | `Runtime._is_workbench` branch in `fire` | delete branch |
| Task-panel slots | `Panel:OK/Apply/Cancel` click the open task panel's buttons | `model.PANEL_PREFIX`, `Runtime._panel_action`, `runtime.panel_open`, picker "Task panel" group | delete those four anchors |
| Live slot editing | right-click a slot in an open pie to edit it | `PieWidget._slot_menu`, `_live_edit` | delete both |
| 1-9 keys + digit tags | number keys fire slots, corner tags show which | digit block in `PieWidget.build`, `keyPressEvent` | delete both |
| Shift chaining | Shift-fire keeps the pie open | sticky check in `PieWidget.activate` | delete the modifier check |
| Last-fired ring | the slot fired last time wears a faint accent border | `model.last_fired`, `[last="true"]` rule in `build`, property in `_slot_button` | delete those three |

## Smart pie

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Smart pie | transient pie of your most-used tools per workbench, decaying counts | `model.bump_stat/top_commands/fill_smart/smart_pie`, `Stats/*` params | delete `SMART_NAME` registration in `Runtime` |
| Favorites | right-click → Keep in Smart; leads the pie, never decays out | `model.smart_favorites`, Smart branch of `_slot_menu`, `Smart/Favorites` param | delete those |
| Ignore list | right-click → Ignore in Smart; counted but never offered | `model.smart_ignored`, same menu, `Smart/Ignored` param, row in `stats_dialog` | delete those |
| Selection-aware ranking | tools you use with a face selected rank first when a face is selected | `axis=` in `bump_stat`, `@axis` stats groups, `dominant_axis`, `counts=` through `smart_pie` | drop the `axis` params; `@` groups age out via decay |

## Pinned palettes

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Pinning | P (or pies-list menu) turns a pie into a floating palette inside the main window | `pinned=` in `PieWidget.__init__`, `Runtime.pin_pie/register_pin`, `dialog._pin_current` | delete those; also the P branch in `keyPressEvent` |
| Selection refresh | pinned palettes re-resolve when the selection settles | `Runtime._selection_settled` loop | delete the loop body |
| Drag to move | drag anywhere on the palette | `_drag_at` in mouse events | delete |
| Edge snap + tuck-away | dropped near an edge it snaps flush; mouse-leave folds it to a slim tab, hover reopens | `_snap_to_edge`, `leaveEvent/enterEvent`, `_collapse/_expand`, collapsed branch in `paintEvent` | delete all five (snap and tuck fall together) |

## Look

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Shapes + styles | rounded/square/squircle/circle; flat/gradient/outline | `runtime.shape_radius`, style css in `build` | keep flat+rounded, delete the rest |
| Colors | global Accent/Outline/Fill/Arrow + per-pie accent | `runtime.custom_color`, `dialog.colors_dialog` | delete dialog + params |
| Outlined overlay text | centre name, hints, digit tags drawn with a contrast rim | `runtime.HaloLabel` | swap back to QLabel |
| Names under buttons | per-pie `show_names`, layout spreads to fit | `show_names` branches in `_slot_button`/`build` | uncheck per pie |
| Gesture arrow | minimal centre→cursor arrow in hold mode | `PieWidget.paintEvent` tail | delete the paint block |

## Preferences

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Non-modal window | preferences float next to FreeCAD, singleton | `dialog.open_preferences`, `_open_dialog` | swap `show()` for `exec_()` |
| Shortcuts table | key × workbench grid, per-gesture lines, inheritance shown | `dialog.ShortcutsTable` | core, keep |
| Table search box | filter rows by key or pie name | `ShortcutsTable.search`, `_apply_filter` | delete both |
| Conflict badges | ⚠ where a bound key shadows a FreeCAD shortcut | `dialog.freecad_shortcuts`, badge block in `rebuild` | delete both |
| Session revert | restore everything to window-open state | `_session_snapshot` in `__init__`, `revert_session` in footer | delete both |
| Keys cheat sheet | Keys… button, every key on one page | `dialog.keys_dialog` | delete + footer button |
| Usage stats panel | Stats… button, top tools + reset | `dialog.stats_dialog` | delete + footer button |
| Live preview | union view, chooser flash, names spread | `dialog.PiePreview` | core-ish |
| Auto-open on selection | opt-in: selection matching a conditional slot opens the pie | `Runtime._auto_open`, `AutoOpenSelection` param | already opt-in |

## Sharing

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Single-pie export/import | `.piemenu.json` with a `requires` list | `dialog.pie_export/pie_import_file`, `missing_requirements` | core of sharing |
| Requires degradation | missing workbenches warn at import, buttons go dead with a reason | `runtime.prefix_available/command_available`, guard in `_decorate` | keep |
| Preset provenance | reinstalling from the same source updates in place | `Pie.source`, `replacing` in `pie_import_file` | delete both |
| Community browser | list + install from the shared GitHub repo | `dialog.browse_presets_dialog`, `PRESET_INDEX` | delete both |
| Whole-setup bundles | every pie + the keybinds in one file, merge-import | `dialog.setup_export/setup_import` | delete both |
