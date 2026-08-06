"""Headless tests for piemenu.dialog: construction against real isolated
params, panel population, tags, the shortcuts table's inheritance styling,
rule widgets and the picker.  Runs under freecadcmd via ``nix run .#smoke``."""
import os
import sys

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from PySide import QtGui, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import FreeCAD as App

from piemenu import dialog, model
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
assert any(t == "Sub" for t in labels), labels          # reached by a door
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
table = dlg.shortcuts
assert table.keys() == ["F6", "F7"]
assert table.left.rowCount() == 2
assert table.right.columnCount() == 2
row_f6 = table.keys().index("F6")
pd_col = table.workbenches.index("PartDesign")
inherited = table.right.item(row_f6, pd_col)
assert inherited.text() == "Main" and inherited.font().italic()
own = table.right.item(table.keys().index("F7"), pd_col)
assert own.text() == "Sub" and not own.font().italic()
sk_col = table.workbenches.index("Sketcher")
assert table.right.item(table.keys().index("F7"), sk_col).text() == "—"
print("PASS shortcuts table")

# ---- opened by --------------------------------------------------------------
dlg.select_pie("Sub")
area_text = []
body = dlg.settings_area.widget()
for label in body.findChildren(QtWidgets.QLabel):
    area_text.append(label.text())
for btn in body.findChildren(QtWidgets.QPushButton):
    area_text.append(btn.text())
joined = " | ".join(area_text)
assert "key F7: in PartDesign" in joined, joined
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
print("PASS edits")

# ---- rule field -------------------------------------------------------------
field = dialog.RuleField({"Face": (">=", 2)})
assert field.preset.currentText() == "two or more faces"
field._change("Edge", (">=", 1))
assert field.preset.currentText() == "Custom…"
assert dialog.rule_text(field.rule) == "Edge >= 1 · Face >= 2"
field._remove("Edge")
field._remove("Face")
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

# ---- behaviour dialog constructs --------------------------------------------
bd = dialog.behaviour_dialog(None)
assert isinstance(bd, QtWidgets.QDialog)
print("PASS behaviour dialog")

ROOT.RemGroup("V2")
print("DIALOG-TESTS-PASS")
