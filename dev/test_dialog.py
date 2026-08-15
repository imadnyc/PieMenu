"""Headless tests for piemenu.dialog: construction against real isolated
params, panel population, tags, the shortcuts table's inheritance styling,
rule widgets and the picker.  Runs under freecadcmd via ``nix run .#smoke``."""
import os
import sys

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from PySide import QtCore, QtGui, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import FreeCAD as App

from piemenu import dialog, model, runtime
from piemenu.model import Binding, Pie

ROOT = App.ParamGet("User parameter:BaseApp/PieMenu")
ROOT.RemGroup("V2")

# ---- seed a small real config ----------------------------------------------
main = Pie("Main", slots=6, per_ring=6, default=True)
model.normalise(main)
main.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                 Binding("PartDesign_Pocket", {"Face": (">=", 1)})]
main.items[1] = [Binding("Std_Undo")]
main.items[2] = [Binding("PieMenu_Sub", {"Edge": (">=", 1)})]
sub = Pie("Sub", slots=4, per_ring=4)
model.normalise(sub)
sub.items[0] = [Binding("Std_Redo")]
orphan = Pie("Orphan", slots=4, per_ring=4)
model.normalise(orphan)
for pie in (main, sub, orphan):
    model.save_pie(pie)
model.set_bind(model.ANY_SCOPE, "F6", "Main")
model.set_bind("PartDesign", "F7", "Sub")

changes = []
dlg = dialog.PieMenuPreferences(
    on_change=lambda: changes.append(1),
    workbenches=["PartDesign", "Sketcher"])

# ---- pies list with tags ----------------------------------------------------
labels = [dlg.pie_list.item(i).text() for i in range(dlg.pie_list.count())]
assert any(t.startswith("Main") and "(default)" in t for t in labels), labels
assert any(t.startswith("Orphan") and "(unused)" in t for t in labels), labels
assert any(t.startswith("Sub") for t in labels), labels  # reached by a door
print("PASS pie list")

# ---- slots table ------------------------------------------------------------
dlg.select_pie("Main")
assert dlg.slots.topLevelItemCount() == 6
top0 = dlg.slots.topLevelItem(0)
assert "2 tools, first match wins" in top0.text(0)
assert top0.child(0).text(1) == "Face >= 1"
door_row = dlg.slots.topLevelItem(2).child(0)
assert door_row.text(0) == "▸ Sub" and door_row.text(1) == "Edge >= 1"
print("PASS slots table")

# ---- shortcuts table --------------------------------------------------------
model.set_bind("PartDesign", "F6", "Sub", "double")   # a second gesture on F6
dlg._binds_changed()
app.processEvents()
table = dlg.shortcuts
assert table.keys() == ["F6", "F7"]
assert table.left.rowCount() == 2
assert table.right.columnCount() == 2
row_f6 = table.keys().index("F6")
pd_col = table.workbenches.index("PartDesign")
cell = table.right.cellWidget(row_f6, pd_col).text()
assert "↳ Main" in cell, cell           # the tap flows in from Any, marked
assert "Sub" in cell                     # the hold is its own line
own = table.right.cellWidget(table.keys().index("F7"), pd_col).text()
assert "Sub" in own and "↳" not in own
sk_col = table.workbenches.index("Sketcher")
sk = table.right.cellWidget(table.keys().index("F7"), sk_col).text()
assert "—" in sk                         # unbound gesture line
model.clear_bind("PartDesign", "F6", "double")
dlg._binds_changed()
app.processEvents()
print("PASS shortcuts table")

# ---- rekeying onto a taken key: swap, or take it over ------------------------
table._move_key("F6", "F7", swap=True)
dlg._binds_changed()
app.processEvents()
binds = model.load_binds()
assert binds[model.ANY_SCOPE]["F7"]["press"] == "Main", binds
assert binds["PartDesign"]["F6"]["press"] == "Sub", binds
table._move_key("F6", "F7")            # no swap: F7's own bind is dropped
dlg._binds_changed()
app.processEvents()
binds = model.load_binds()
assert binds["PartDesign"]["F7"]["press"] == "Sub", binds
assert "F6" not in binds["PartDesign"] and "F6" not in binds[model.ANY_SCOPE]
assert "press" not in binds[model.ANY_SCOPE].get("F7", {}), binds
model.remove_key("F7")
model.set_bind(model.ANY_SCOPE, "F6", "Main")
model.set_bind("PartDesign", "F7", "Sub")
dlg._binds_changed()
app.processEvents()
print("PASS rekey conflict")

# ---- opened by --------------------------------------------------------------
dlg.select_pie("Sub")
area_text = []
body = dlg.settings_area.widget()
for label in body.findChildren(QtWidgets.QLabel):
    area_text.append(label.text())
for btn in body.findChildren(QtWidgets.QPushButton):
    area_text.append(btn.text())
joined = " | ".join(area_text)
assert "key F7 (press): in PartDesign" in joined, joined
assert "from Main — slot 3, Edge >= 1" in joined, joined
print("PASS opened by")

# ---- edits round-trip through params ----------------------------------------
dlg.select_pie("Main")
changes.clear()
dlg._swap(0, 4)                       # drag slot 1 -> slot 5
assert changes and model.load_pie("Main").items[4][0].cmd == "PartDesign_Pad"
dlg._swap(0, 4)                       # put it back
dlg._remove_binding(1, 0)             # drop Undo
assert model.load_pie("Main").items[1] is None
main2 = dlg.pie()
main2.items[1] = [Binding("Std_Undo")]
dlg._changed(True)
assert model.load_pie("Main").items[1][0].cmd == "Std_Undo"
dlg._set("radius", 123)
assert model.load_pie("Main").radius == 123
# structural rebuilds are deferred one tick: a synchronous refresh() destroys
# the sender widget mid-signal (the grid/circle combo segfaulted this way)
dlg._set_family("grid")
assert dlg._refresh_queued, "family change must queue, not rebuild in place"
assert model.load_pie("Main").family == "grid"   # the save itself is immediate
app.processEvents()
assert not dlg._refresh_queued
dlg._set_family("circle")
app.processEvents()
# the context checker surfaces in the tree: conditional + always in one slot
orig_slot = dlg.pie().items[2]
dlg.pie().items[2] = [Binding("Std_New", {"Face": (">=", 2)}),
                      Binding("Std_Open")]
dlg._fill_slots()
texts = [dlg.slots.topLevelItem(k).text(0)
         for k in range(dlg.slots.topLevelItemCount())]
assert any("context clash" in t for t in texts), texts
dlg.pie().items[2] = orig_slot
dlg._fill_slots()
# shrinking stashes what fell off; growing back within the dialog restores it
kept = dlg.pie().items[1]
assert kept, "test wants slot 2 occupied"
old_n = dlg.pie().slots
dlg._set("slots", 1, structure=True)
app.processEvents()
assert len(model.load_pie("Main").items) == 1        # the shrink saved small
dlg._set("slots", old_n, structure=True)
app.processEvents()
assert dlg.pie().items[1] == kept                    # ...but nothing was lost
assert model.load_pie("Main").items[1][0].cmd == kept[0].cmd
print("PASS edits")

# ---- rule field -------------------------------------------------------------
field = dialog.RuleField({"Face": (">=", 2)})
tick, sign, num = field.axis_rows["Face"]
assert tick.isChecked() and sign.currentText() == ">=" and num.value() == 2
etick, esign, enum = field.axis_rows["Edge"]
assert not etick.isChecked() and not esign.isEnabled()
etick.setChecked(True)                       # a fresh tick defaults to >= 1
assert field.rule == {"Edge": (">=", 1), "Face": (">=", 2)}
assert dialog.rule_text(field.rule) == "Edge >= 1 · Face >= 2"
enum.setValue(3)
assert field.rule["Edge"] == (">=", 3)
tick.setChecked(False)                       # untick drops the constraint
assert "Face" not in field.rule and "always" not in field.reads.text()
etick.setChecked(False)                      # untick the last one
assert field.rule == {}
assert dialog.rule_text(field.rule) == "always"
print("PASS rule field")

# ---- picker -----------------------------------------------------------------
actions = {}
for name in ("Std_Undo", "Std_Redo", "PartDesign_Pad"):
    act = QtGui.QAction(name)
    act.setObjectName(name)
    actions[name] = act
picker = dialog.PickerDialog(dlg.pies, dlg.pie(), dlg.pie().items[0],
                             actions=actions)
groups = [picker.tree.topLevelItem(i).text(0)
          for i in range(picker.tree.topLevelItemCount())]
assert any(g.startswith("Std") for g in groups), groups
assert any(g.startswith("Pie menus") for g in groups), groups
picker.search.setText("redo")
hits = []
for i in range(picker.tree.topLevelItemCount()):
    top = picker.tree.topLevelItem(i)
    hits += [top.child(j) for j in range(top.childCount())]
assert len(hits) == 1 and hits[0].text(0) == "Redo"
picker._picked(hits[0], 0)
picker.rule.rule = {"Object": (">=", 2)}
binding = picker.result_binding()
assert binding.cmd == "Std_Redo" and binding.rule == {"Object": (">=", 2)}
assert "Redo" in picker.echo.text()
print("PASS picker")

# ---- the auto ring readout follows the arc slider live -----------------------
dlg.select_pie("Main")
dlg._set("radius", 80)                   # earlier tests moved it
dlg._set("ring_mode", "auto", structure=True)
app.processEvents()
before = dlg._auto_plan_label.text()
dlg._set("arc", 120)                     # non-structural slider write
after = dlg._auto_plan_label.text()
assert before != after, (before, after)  # fewer degrees, tighter rings
dlg._set("arc", 360)
dlg._set("ring_mode", "uniform", structure=True)
app.processEvents()

# ---- the chooser-size knob demos a mock chooser in the preview ---------------
dlg.select_pie("Main")
dlg._set("alt_size", 36)
assert dlg.preview._mock_chooser is not None
assert dlg.preview._mock_chooser[1] == 36
dlg.preview._unflash()
assert dlg.preview._mock_chooser is None

# ---- community preset browser (against a local file:// index) ---------------
import json
import tempfile

tmp = tempfile.mkdtemp(prefix="pm-presets-")
os.makedirs(os.path.join(tmp, "presets"))
net_pie = {"name": "NetPie", "family": "circle", "slots": 2, "per_ring": 2,
           "requires": ["NoSuchBench"],
           "items": [[{"cmd": "Std_New", "rule": "", "label": ""}], []]}
with open(os.path.join(tmp, "presets", "NetPie.piemenu.json"), "w") as fh:
    json.dump(net_pie, fh)
with open(os.path.join(tmp, "index.json"), "w") as fh:
    json.dump({"format": 1, "presets": [
        {"name": "NetPie", "author": "t", "description": "d",
         "file": "presets/NetPie.piemenu.json",
         "requires": ["NoSuchBench"]}]}, fh)
dialog.PRESET_INDEX = "file://" + tmp + "/"
bd = dialog.browse_presets_dialog(
    dlg, lambda p, **kw: dlg.pie_import_file(p, confirm=False, **kw))
lw = bd.findChild(QtWidgets.QListWidget)
assert lw.count() == 1 and "NetPie" in lw.item(0).text()
lw.setCurrentRow(0)
install_btn = next(b for b in bd.findChildren(QtWidgets.QPushButton)
                   if b.text() == "Install")
install_btn.click()
assert "NetPie" in dlg.pies
assert dlg.pies["NetPie"].items[0][0].cmd == "Std_New"
assert dlg.pies["NetPie"].source.startswith("file://")
# installing the same preset again updates in place, no NetPie-2
install_btn.click()
assert "NetPie" in dlg.pies and "NetPie-2" not in dlg.pies
assert model.load_pies()["NetPie"].source == dlg.pies["NetPie"].source
bd.deleteLater()
print("PASS preset browser")

# ---- requires: classification and junk tolerance -----------------------------
assert dialog.missing_requirements({}) == []
assert dialog.missing_requirements({"requires": "PartDesign"}) == []  # junk
assert dialog.missing_requirements({"requires": [3, None, "", "  "]}) == []
assert dialog.missing_requirements(
    {"requires": ["Macro:definitely-absent.FCMacro"]}) == \
    ["Macro:definitely-absent.FCMacro"]
# headless prefix checks are permissive, so bench prefixes never block here
assert dialog.missing_requirements({"requires": ["NoSuchBenchXYZ"]}) == []

# stress: a huge preset with junk fields imports whole and fast
big_data = {"name": "Huge", "family": "circle", "slots": 48, "per_ring": 8,
            "requires": [f"Bench{i}" for i in range(30)],
            "unknown_future_field": {"nested": [1, 2, 3]},
            "items": [[{"cmd": f"Bench{i % 7}_T{i}", "rule": "Face >= 1",
                        "label": f"L{i}", "extra": "junk"}]
                      for i in range(48)]}
big_path = os.path.join(tempfile.mkdtemp(prefix="pm-big-"), "h.piemenu.json")
with open(big_path, "w") as fh:
    json.dump(big_data, fh)
dlg.pie_import_file(big_path, confirm=False)
assert "Huge" in dlg.pies
assert sum(1 for s in dlg.pies["Huge"].items if s) == 48
assert dlg.pies["Huge"].items[3][0].label == "L3"
assert dlg.pies["Huge"].items[3][0].rule == {"Face": (">=", 1)}
dlg.pies_delete(["Huge"], confirm=False)

# malformed rule text must fail the import without crashing the dialog
bad_path = big_path + ".bad"
with open(bad_path, "w") as fh:
    json.dump({"name": "Bad", "items": [[{"cmd": "X_Y",
                                          "rule": "utter garbage"}]]}, fh)
dlg.pie_import_file(bad_path, confirm=False)
assert "Bad" not in dlg.pies
with open(bad_path, "w") as fh:
    fh.write("{not json at all")
dlg.pie_import_file(bad_path, confirm=False)          # parse error: no crash
assert "Bad" not in dlg.pies

# a browser pointed at garbage lists the failure instead of raising
garbage_dir = tempfile.mkdtemp(prefix="pm-garbage-")
with open(os.path.join(garbage_dir, "index.json"), "w") as fh:
    fh.write("]]]] nope")
dialog.PRESET_INDEX = "file://" + garbage_dir + "/"
gb = dialog.browse_presets_dialog(dlg, lambda p, **kw: None)
glw = gb.findChild(QtWidgets.QListWidget)
assert glw.count() >= 1 and "couldn't reach" in glw.item(0).text()
gb.deleteLater()
print("PASS requires stress")

# ---- multi-select delete -----------------------------------------------------
for zname in ("Zed1", "Zed2"):
    model.save_pie(Pie(zname, slots=2, per_ring=2))
dlg.pies = model.load_pies()
dlg._binds_changed()
app.processEvents()
assert "Zed1" in dlg.pies and "Zed2" in dlg.pies
dlg.pies_delete(["Zed1", "Zed2", model.SMART_NAME], confirm=False)
assert "Zed1" not in dlg.pies and "Zed2" not in dlg.pies
assert model.SMART_NAME in dlg.pies          # Smart is not deletable
print("PASS multi delete")

# ---- shipped presets import cleanly ------------------------------------------
preset_dir = os.path.join(os.environ.get("PIEMENU_REPO",
                                         "/home/dre/Projects/PieMenu"),
                          "presets")
if os.path.isdir(preset_dir):
    for fname in sorted(os.listdir(preset_dir)):
        if fname.endswith(".piemenu.json"):
            dlg.pie_import_file(os.path.join(preset_dir, fname))
    assert "PartDesignMisc" in dlg.pies
    assert any(s for s in dlg.pies["PartDesignMisc"].items if s)
    print("PASS presets")

# ---- whole-setup bundle: export, then merge without clobbering ---------------
setup_path = os.path.join(tempfile.mkdtemp(prefix="pm-setup-"),
                          "s.piemenu-setup.json")
dlg.setup_export(setup_path)
with open(setup_path) as fh:
    sdata = json.load(fh)
assert sdata["format"] == "piemenu-setup-1"
assert any(p["name"] == "Main" for p in sdata["pies"])
assert all(p["name"] != model.SMART_NAME for p in sdata["pies"])
assert sdata["binds"]                    # the keybinds ride along
dlg.pies_delete(["Sub"], confirm=False)
assert "Sub" not in dlg.pies
summary = dlg.setup_import(setup_path, confirm=False)
assert "Sub" in summary["added"]         # the deleted pie came back
assert "Main" in summary["skipped"]      # the existing one was kept
assert summary["bound"] == 0             # every bind was already taken
assert "Sub" in dlg.pies and "Sub" in model.load_pies()
# a garbage file reports failure instead of raising
with open(setup_path, "w") as fh:
    fh.write("{nope")
assert dlg.setup_import(setup_path, confirm=False) is None
print("PASS setup bundle")

# ---- mouse buttons: the recorder answers to a thumb click --------------------
mdlg = QtWidgets.QDialog()
mcaught = {}
mc = dialog._MouseCatch(mdlg, mcaught)
press4 = QtGui.QMouseEvent(
    QtCore.QEvent.MouseButtonPress, QtCore.QPointF(0, 0),
    QtCore.QPointF(0, 0), QtCore.Qt.XButton1, QtCore.Qt.XButton1,
    QtCore.Qt.NoModifier)
assert mc.eventFilter(None, press4) and mcaught["key"] == "Mouse4"
mdlg.deleteLater()
# headless there is no main window, so the conflict map is just empty
assert dialog.freecad_shortcuts() == {}
print("PASS mouse capture")

# ---- session snapshot backs the Revert button --------------------------------
if dlg._session_snapshot:
    assert os.path.exists(dlg._session_snapshot)
    model.save_pie(Pie("EphemeralJunk", slots=2, per_ring=2))
    assert "EphemeralJunk" in model.load_pies()
    App.ParamGet("User parameter:BaseApp/PieMenu").Import(
        dlg._session_snapshot)
    assert "EphemeralJunk" not in model.load_pies()
    print("PASS session revert")

# ---- preferences window is non-modal and a singleton --------------------------
win = dialog.open_preferences()
assert win.isVisible()                       # show(), not exec_()
assert dialog.open_preferences() is win      # second call refocuses
win.close()
win.deleteLater()
app.processEvents()
print("PASS non-modal prefs")

# ---- table search box filters by key and by pie name -------------------------
tbl = dlg.shortcuts
tbl.search.setText("f7")
vis = [r for r in range(tbl.left.rowCount()) if not tbl.left.isRowHidden(r)]
assert vis == [tbl.keys().index("F7")]
tbl.search.setText("sub")                    # matches the pie name
vis = [r for r in range(tbl.left.rowCount()) if not tbl.left.isRowHidden(r)]
assert tbl.keys().index("F7") in vis
tbl.search.setText("")
assert not any(tbl.left.isRowHidden(r) for r in range(tbl.left.rowCount()))
print("PASS table search")

# ---- Run: binds read as commands in the table --------------------------------
assert dialog.bind_label("Run:Sketcher_ConstrainRadius") \
    == "⚡ ConstrainRadius"
assert dialog.bind_label("Main") == "Main"
assert "no pie" in dialog.bind_tip("Run:Std_New")
print("PASS run bind labels")

# ---- GifTip: hovering plays the movie, leaving stops it ----------------------
from PIL import Image as PILImage

tiny_dir = tempfile.mkdtemp(prefix="pm-gif-")
tiny = os.path.join(tiny_dir, "tiny.gif")
frame = PILImage.new("P", (8, 8))
frame.save(tiny, save_all=True, append_images=[PILImage.new("P", (8, 8))],
           duration=50, loop=0)
gif_holder = QtWidgets.QWidget()
gif_btn = QtWidgets.QToolButton(gif_holder)
gif_btn.setToolTip("what this does")
tip = dialog.GifTip(gif_btn, "does-not-exist")
assert gif_btn.toolTip() == "what this does"  # no movie: tooltip stays
app.sendEvent(gif_btn, QtCore.QEvent(QtCore.QEvent.Enter))
assert tip._pop is None                      # missing movie: quiet no-op
tip._path = tiny
app.sendEvent(gif_btn, QtCore.QEvent(QtCore.QEvent.Enter))
assert tip._pop is not None
labels = tip._pop.findChildren(QtWidgets.QLabel)
assert any(lb.movie() is not None for lb in labels)   # the movie plays
assert any(lb.text() == "what this does" for lb in labels)
app.sendEvent(gif_btn, QtCore.QEvent(QtCore.QEvent.Leave))
assert tip._pop is None
gif_holder.deleteLater()
print("PASS gif tip")

# ---- task panel pseudo-commands surface in labels and the picker -------------
assert dialog.command_label("Panel:OK") == "OK (task panel)"
assert dlg._pie_dict(dlg.pies["Main"]).get("door_instant") is False
print("PASS panel labels")

# ---- the editor flags rings wider than eight ---------------------------------
dlg.select_pie("Main")
dlg.pies["Main"].slots = 12
dlg.pies["Main"].per_ring = 12
model.save_pie(dlg.pies["Main"])
dlg.refresh()
app.processEvents()
assert not dlg._wide_hint.isHidden()         # 12-wide ring: hint shows
dlg.pies["Main"].slots = 6
dlg.pies["Main"].per_ring = 6
model.save_pie(dlg.pies["Main"])
dlg.refresh()
app.processEvents()
assert dlg._wide_hint.isHidden()
print("PASS wide-ring hint")

# ---- the Doctor finds what's broken ------------------------------------------
sick = Pie("Sick", slots=2, per_ring=2)
model.normalise(sick)
sick.items[0] = [Binding("PieMenu_NoSuchDoor")]
sick.items[1] = [Binding("Macro:definitely-absent.FCMacro")]
dlg.pies["Sick"] = sick
model.set_bind("PartDesign", "F11", "GhostPie")
findings = dialog.doctor_findings(dlg.pies, model.load_binds())
assert any("NoSuchDoor" in f for f in findings)
assert any("definitely-absent" in f for f in findings)
assert any("GhostPie" in f for f in findings)
dd = dialog.doctor_dialog(dlg, dlg.pies, model.load_binds())
assert dd.findChildren(QtWidgets.QListWidget)
dd.deleteLater()
model.remove_key("F11")
del dlg.pies["Sick"]
print("PASS doctor")

# ---- the keys cheat sheet builds and names the essentials --------------------
kd = dialog.keys_dialog(dlg)
kd_text = " ".join(lb.text() for lb in kd.findChildren(QtWidgets.QLabel))
for needle in ("1–9", "Backspace", "pin", "SketchEdit"):
    assert needle in kd_text, f"keys dialog misses {needle}"
kd.deleteLater()
print("PASS keys dialog")

# ---- SketchEdit is offered as a scope and chains through Sketcher ------------
scopes = dialog.workbench_scopes()
assert model.SKETCH_EDIT_SCOPE in scopes
assert scopes.index(model.SKETCH_EDIT_SCOPE) == \
    scopes.index("Sketcher") + 1

# ---- the global surface is just accent + backup ------------------------------
assert not hasattr(dlg, "g_toggle")      # the behaviour toggles are gone
assert not hasattr(dlg, "g_rclick")
assert not hasattr(dialog, "behaviour_dialog")
print("PASS behaviour dialog")

# ---- the Edit > Preferences page round-trips its params ----------------------
page = dialog.PreferencePage()
p = App.ParamGet(runtime.MAIN)
p.SetString("Theme", "dark")
p.SetBool("AutoOpenSelection", True)
page.loadSettings()
assert page.theme.currentIndex() == 2 and page.auto_open.isChecked()
page.theme.setCurrentIndex(1)
page.auto_open.setChecked(False)
page.saveSettings()
assert p.GetString("Theme", "") == "light"
assert not p.GetBool("AutoOpenSelection", True)
p.SetString("Theme", "")
print("PASS preference page")

ROOT.RemGroup("V2")
print("DIALOG-TESTS-PASS")
