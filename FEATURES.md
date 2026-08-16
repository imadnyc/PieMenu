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
| Hold = marking menu | a pie opened by a HOLD always runs as a marking menu, whatever its own run_on | `mode="release"` in `Dispatcher._open_deferred`, `mode` param through `open_pie`/`PieWidget` | stop passing the mode |
| Mark-ahead | a stroke completed before the pie renders fires blind, compound marks continue through doors (3 levels), a 300ms stroke ghost confirms | `Runtime.blind_fire`, `_StrokeGhost`, the `moved` branch of `Dispatcher._release` | delete those three; strokes then fall back to opening the pie |
| Key-up timeout | no release AND no motion for 2s = a device that never sends key-up: the pie demotes to click mode | `Dispatcher._keyup_guard`, `STUCK_MS` | delete the timer |
| Letter accels | a binding's one-letter accel fires its slot while the pie is open (shown as an accent tag, beats P-to-pin) | `Binding.accel`, letter branch in `keyPressEvent`, "Shortcut letter…" in `_slot_menu` | delete those |
| Mouse thumb buttons | Mouse4/Mouse5 bind like keys, all gestures | `runtime.MOUSE_KEYS`, mouse branches in `Dispatcher.eventFilter`, `dialog._MouseCatch` | delete those three |
| Right-click trigger | long right-click opens the resolved pie | `Dispatcher._arm_rclick`, `RightClickTrigger` param | delete methods + param |
| Run binds | a gesture runs one command instead of opening a pie (tap = Constrain Radius, hold = the pie) | `model.RUN_PREFIX`, Run branches in `Dispatcher`, `_bind_command` in the table | delete those three |
| Angular aim | circle pies read the gesture as a direction: radius picks the ring, angle the slot; dead/empty sectors are no-ops; ~5° boundary stickiness | `PieWidget._angular_slot`, `_sectors` in `build` | delete both; the Euclidean fallback in `nearest_slot` takes over |
| Aim feedback | the aimed slot wears an accent ring and the centre names what release will do ("Cancel" in the dead zone) | `PieWidget._set_aim`, `aimed` rule in `build`, `aimname` property in `_decorate` | delete those three |
| Screen clamp | a pie opened at the screen edge shifts fully on-screen (cursor warps along where the platform allows) | else-branch of `PieWidget.popup_at` | delete the branch |

## Slots and rules

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Selection conditions | per-binding rules over six axes, first match wins | `model.match_rule`, `decode_rule` | core, keep |
| Chooser | overloaded slot pops flavours, remembers last pick, dismisses itself ~750ms after the cursor leaves | `runtime._chooser_widget`, `_watch_chooser`, `last_used` | core-ish; delete `_watch_chooser` to make it sticky again |
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
| Smart pie | transient pie of your most-used tools per workbench, decaying counts, FROZEN positions (first fill fixes the layout; tools are evicted in place, never shuffled; Stats… → Rebuild Smart layout resets) | `model.bump_stat/top_commands/fill_smart/smart_pie`, `smart_layout`, `Stats/*` + `Smart/Layout/*` params | delete `SMART_NAME` registration in `Runtime` |
| Favorites | right-click → Keep in Smart; leads the pie, never decays out | `model.smart_favorites`, Smart branch of `_slot_menu`, `Smart/Favorites` param | delete those |
| Ignore list | right-click → Ignore in Smart; counted but never offered | `model.smart_ignored`, same menu, `Smart/Ignored` param, row in `stats_dialog` | delete those |
| Selection-aware ranking | tools you use with a face selected enter free slots first when a face is selected — entry only, positions stay frozen | `axis=` in `bump_stat`, `@axis` stats groups, `dominant_axis`, `counts=` through `smart_pie` | drop the `axis` params; `@` groups age out via decay |
| On-axis fill | the best-ranked tools land on the cardinal directions before the diagonals | `model._axis_order` in `fill_smart` | delete `_axis_order`, fill 0..n again |

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
| Shapes + styles | rounded/square/squircle/circle; flat/gradient/outline/soft/glass/bold/minimal | `runtime.shape_radius`, style css in `build` | keep flat+rounded, delete the rest |
| Colors + theme | one-click Light/Dark pie theme (Colors…), global Accent/Outline/Fill/Arrow + per-pie accent still win over it | `runtime.THEMES/active_theme`, `runtime.custom_color`, `dialog.colors_dialog` | delete dialog + params |
| Overlay text | centre name + hints on a flat pill of the theme's window color, digit/accel tags bare; all follow the theme's text color (palette when following FreeCAD) | `runtime.HaloLabel`, `_halo`/`_chip` in `build` | swap back to QLabel |
| Opaque fallback | without a compositor translucent pies render black; the OpaquePies switch (Colors…) paints a solid rounded panel | `_opaque` in `PieWidget`, checkbox in `colors_dialog`, `OpaquePies` param | delete those |
| Names under buttons | per-pie `show_names`, layout spreads to fit | `show_names` branches in `_slot_button`/`build` | uncheck per pie |
| Gesture arrow | minimal centre→cursor arrow in hold mode | `PieWidget.paintEvent` tail | delete the paint block |

## Preferences

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Non-modal window | preferences float next to FreeCAD, singleton | `dialog.open_preferences`, `_open_dialog` | swap `show()` for `exec_()` |
| Preferences page | Edit ▸ Preferences ▸ PieMenu: theme, auto-open, and the way into the editor (replaces the Tools ▸ Accessories timer hack) | `dialog.PreferencePage`, registration in `InitGui`, `Resources/icons/preferences-piemenu.svg` | delete all three |
| Shortcuts table | key × workbench grid, per-gesture lines, inheritance shown | `dialog.ShortcutsTable` | core, keep |
| Table search box | filter rows by key or pie name | `ShortcutsTable.search`, `_apply_filter` | delete both |
| Key clash prompt | rekeying onto a taken key offers swap / unbind instead of doing nothing | `ShortcutsTable._rekey`, `_move_key`, `_key_opens` | drop the prompt, keep `_move_key` |
| Conflict badges | ⚠ where a bound key shadows a FreeCAD shortcut | `dialog.freecad_shortcuts`, badge block in `rebuild` | delete both |
| Session revert | restore everything to window-open state | `_session_snapshot` in `__init__`, `revert_session` in footer | delete both |
| Keys cheat sheet | Keys… button, every key on one page | `dialog.keys_dialog` | delete + footer button |
| Doctor | Doctor… button: health scan (dead commands, orphaned binds/doors, shadowed keys, wide rings, context lint), the last 12 dispatches, and what each key resolves to right now | `dialog.doctor_findings/doctor_dialog`, `Dispatcher.trace` | delete all three |
| Hover demos | hovering a ? button or keys-page row shows one tooltip bubble with the text AND the demo GIF playing in it (replaces the native tooltip, which cannot animate) | `dialog.GifTip`, movies in `docs/gifs/` rendered by `nix run .#gifs` (`dev/gif_scenes.py`) | delete `GifTip` + call sites; the GIFs are plain files |
| Settings menu | the footer is one ⚙ Settings menu (colors/theme, stats, keys, Doctor, auto-open, export/import/revert) + Close; Add-key lives on the shortcuts panel | the footer block of `PieMenuPreferences.__init__` | inline the buttons again |
| Usage stats panel | Stats… button, top tools + reset | `dialog.stats_dialog` | delete + footer button |
| Live preview | union view, chooser flash, names spread | `dialog.PiePreview` | core-ish |
| Hand-placed slots | drag a slot on the preview: snaps to 15° / 5 px (grid: cell steps), **Shift = free placement**, drop on a slot swaps, overlapping drops are refused with the reason | `Pie.placed`, `model._place`, drag handlers + `_snap` in `PreviewWidget`, `_slot_placed` | delete those + the `Pos` slot param |
| Layout lock | per-pie switch: preview drags are refused (context menu of the pie list) | `Pie.layout_lock`, `_lock_layout`, lock check in `mouseMoveEvent` | delete all three |
| Reset positions | per-slot (slot context menu) and whole-pie (pie context menu) return to the computed layout | `_reset_position`, `_reset_positions` | delete both |
| Wide-ring hint | a quiet note when a ring exceeds 8 slots, pointing at door slots | `_wide_hint` in the layout panel + `_fill_settings_labels` | delete both |
| Auto-open on selection | opt-in: selection matching a conditional slot opens the pie | `Runtime._auto_open`, `AutoOpenSelection` param | already opt-in |

## Sharing

| Feature | What | Lives in | Remove |
|---|---|---|---|
| Single-pie export/import | `.piemenu.json` with a `requires` list | `dialog.pie_export/pie_import_file`, `missing_requirements` | core of sharing |
| Requires degradation | missing workbenches warn at import, buttons go dead with a reason | `runtime.prefix_available/command_available`, guard in `_decorate` | keep |
| Availability cache | yes-answers cached until reload so opens stop re-scanning the registry | `runtime._AVAILABLE`, cleared in `Runtime.reload` | delete the wrappers, keep the `_uncached` bodies |
| Preset provenance | reinstalling from the same source updates in place | `Pie.source`, `replacing` in `pie_import_file` | delete both |
| Community browser | list + install from the shared GitHub repo | `dialog.browse_presets_dialog`, `PRESET_INDEX` | delete both |
| Whole-setup bundles | every pie + the keybinds in one file, merge-import | `dialog.setup_export/setup_import` | delete both |
| Fresh-install starter | a truly fresh profile gets the full starter set (piemenu/starter.py) at first migrate, so F3 works out of the box | fresh branch of `migrate.migrate` | seed a single bare pie again |
