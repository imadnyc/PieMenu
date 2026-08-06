"""Headless tests for piemenu.runtime: the pie widget, resolution against
selection counts, doors, the chooser, hover firing, and key dispatch.
Runs under freecadcmd (offscreen) via ``nix run .#smoke``."""
import os
import sys
import time

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from PySide import QtCore, QtGui, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import FreeCAD as App

from piemenu import model, runtime
from piemenu.model import Binding, Pie


def wait(ms):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def make_pies():
    main = Pie("Main", slots=8, per_ring=8)
    model.normalise(main)
    main.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                     Binding("PartDesign_Fillet", {"Edge": (">=", 1)})]
    main.items[1] = [Binding("Std_Undo")]
    main.items[2] = [Binding("PieMenu_Sub")]
    main.items[3] = [Binding("PartDesign_Groove", {"Face": ("==", 1)})]
    main.items[4] = [Binding("Std_New"), Binding("Std_Open")]   # chooser
    sub = Pie("Sub", slots=4, per_ring=4)
    model.normalise(sub)
    sub.items[0] = [Binding("Part_Cut", {"Object": (">=", 2)})]
    sub.items[1] = [Binding("Std_Redo")]
    return {"Main": main, "Sub": sub}


fired = []


def fire(cmd):
    fired.append(cmd)


# ---- resolution drives the buttons ----------------------------------------
pies = make_pies()
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
vis = [b for b in w.buttons if not b.isHidden()]
assert len(vis) == 5, len(vis)                       # 5 filled slots
b0, b1, b2, b3, b4 = w.buttons[:5]
assert b0.isEnabled() and "Pad" in b0.toolTip()      # face -> Pad
assert b3.isEnabled()                                # Groove on exactly 1 face
assert b2.isEnabled() and "Open Sub" in b2.toolTip() # door, live via Redo
w.deleteLater()

w = runtime.PieWidget(pies, "Main", {"Face": 2}, fire)
assert not w.buttons[3].isEnabled()                  # Groove drops on 2 faces
assert "Pad" in w.buttons[0].toolTip()
w.deleteLater()

w = runtime.PieWidget(pies, "Main", {"Edge": 1}, fire)
assert "Fillet" in w.buttons[0].toolTip()            # same slot, other binding
w.deleteLater()
print("PASS widget resolution")

# ---- firing and doors ------------------------------------------------------
fired.clear()
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.buttons[1].click()
assert fired == ["Std_Undo"], fired
assert not w.isVisible()                             # ran -> closed
w.deleteLater()

fired.clear()
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.buttons[2].click()                                 # the door
assert w.pie.name == "Sub" and fired == []           # descended, nothing ran
assert w.isVisible()
# the sub-pie's buttons were born on an already-visible parent: they must
# have been shown explicitly, or the "spawned" pie is an empty ghost
assert any(not b.isHidden() for b in w.buttons), "sub-pie buttons invisible"
w.close()
w.deleteLater()
print("PASS firing and doors")

# ---- chooser ---------------------------------------------------------------
fired.clear()
w = runtime.PieWidget(pies, "Main", {}, fire)        # nothing selected
live = model.live_bindings(pies["Main"].items[4], {})
assert len(live) == 2
w.show_chooser(w.buttons[4], live)
alts = w._chooser.findChildren(QtWidgets.QToolButton)
assert len(alts) == 2
alts[1].click()
assert fired == ["Std_Open"], fired
w.deleteLater()
print("PASS chooser")

# ---- hover firing ----------------------------------------------------------
fired.clear()
pies["Main"].run_on = "hover"
pies["Main"].delay = 60
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
app.sendEvent(w.buttons[1], QtCore.QEvent(QtCore.QEvent.Enter))
wait(150)
assert fired == ["Std_Undo"], fired
w.deleteLater()
pies["Main"].run_on = "click"
print("PASS hover")

# ---- gesture aiming --------------------------------------------------------
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
centre = w.buttons[1].mapToGlobal(QtCore.QPoint(17, 17))
assert w.nearest_slot(centre) is w.buttons[1]
far = w.mapToGlobal(QtCore.QPoint(-2000, -2000))
assert w.nearest_slot(far) is None
w.close()
w.deleteLater()
print("PASS gesture aim")

# ---- gesture release: faces, choosers, sticky picks ------------------------
fired.clear()
pies["Main"].last_used.clear()
pies["Main"].run_on = "release"
w = runtime.PieWidget(pies, "Main", {}, fire)        # slot 4 has 2 live
w.popup_at(QtCore.QPoint(400, 400))
aim = w.buttons[4].mapToGlobal(QtCore.QPoint(17, 17))
w.commit_gesture(pos=aim)                # overloaded slot fires its face
assert fired == ["Std_New"], fired
assert not w.isVisible()
w.deleteLater()

fired.clear()
w = runtime.PieWidget(pies, "Main", {}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.show_chooser(w.buttons[4], model.live_bindings(pies["Main"].items[4], {}))
alts = w._chooser.findChildren(QtWidgets.QToolButton)
over_alt = alts[1].mapToGlobal(QtCore.QPoint(12, 12))
w.commit_gesture(pos=over_alt)           # release over the second flavour
assert fired == ["Std_Open"], fired
assert not w.isVisible()
w.deleteLater()

fired.clear()                            # the pick sticks: face is now Open
assert pies["Main"].last_used[4] == "Std_Open"
w = runtime.PieWidget(pies, "Main", {}, fire)
w.popup_at(QtCore.QPoint(400, 400))
assert "Open" in w.buttons[4].toolTip()
w.commit_gesture(pos=w.buttons[4].mapToGlobal(QtCore.QPoint(17, 17)))
assert fired == ["Std_Open"], fired
w.deleteLater()
pies["Main"].run_on = "click"
pies["Main"].last_used.clear()
print("PASS gesture faces")


# ---- dispatcher ------------------------------------------------------------
class FakePie:
    def __init__(self, open_on, run_on):
        self.open_on, self.run_on = open_on, run_on


class FakeWidget:
    def __init__(self, pie):
        self.pie = pie
        self.visible = True
        self.committed = False

    def isVisible(self):
        return self.visible

    def close(self):
        self.visible = False

    def commit_gesture(self):
        self.committed = True
        self.visible = False


def key_event(kind, key):
    return QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier)


opened = []
meta = {"Main": FakePie("single", "click")}


def opener(name):
    fw = FakeWidget(meta[name])
    opened.append(fw)
    return fw


disp = runtime.Dispatcher(opener, lambda k: "Main" if k == "F6" else None,
                          open_on_of=lambda n: meta[n].open_on)

App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", True)
assert disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert len(opened) == 1 and opened[0].visible
assert disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert len(opened) == 1 and not opened[0].visible    # toggled shut

App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", False)
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert len(opened) == 3                              # reopens instead
App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", True)

opened.clear()
meta["Main"] = FakePie("double", "click")
disp.close()
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert opened == []                                  # one tap arms
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert len(opened) == 1                              # second tap opens

opened.clear()
meta["Main"] = FakePie("hold", "release")
disp.close()
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
assert len(opened) == 1 and opened[0].visible
disp.eventFilter(None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F6))
assert opened[0].committed                           # release fired the aim

opened.clear()
meta["Main"] = FakePie("hold", "click")
disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
disp.eventFilter(None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F6))
assert not opened[0].visible and not opened[0].committed   # momentary close
print("PASS dispatch")


# ---- the Runtime wrapper over real params ----------------------------------
class FakeWb:
    def name(self):
        return "PartDesignWorkbench"


class FakeGui:
    def __init__(self):
        self.commands = {}
        self.ran = []

    def addCommand(self, name, obj):
        self.commands[name] = obj

    def activeWorkbench(self):
        return FakeWb()

    def runCommand(self, cmd, idx=0):
        self.ran.append(cmd)


App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
for pie in make_pies().values():
    model.save_pie(pie)
model.set_bind(model.ANY_SCOPE, "F6", "Main")
model.set_bind("PartDesign", "F7", "Sub")

gui = FakeGui()
rt = runtime.Runtime(gui)
rt.reload()
assert set(gui.commands) == {"PieMenu_Main", "PieMenu_Sub"}
assert rt._resolve("F6") == "Main"
assert rt._resolve("F7") == "Sub"                    # workbench scope
assert rt._resolve(None) == "Main"                   # right-click: lowest key
assert rt.counts() == {}                             # no Selection on the fake
widget = rt.open_pie("Main")
assert widget is not None and widget.isVisible()
rt.fire("Std_Undo")
assert gui.ran == ["Std_Undo"]
widget.close()
print("PASS runtime wrapper")

# ---- keys-only door descend through the real dispatcher --------------------
rt.pies["Main"].open_on = "hold"
rt.pies["Main"].run_on = "release"
gui.ran.clear()
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F6))
w = rt.dispatcher.current
assert w is not None and w.isVisible() and w.pie.name == "Main"
QtGui.QCursor.setPos(w.buttons[2].mapToGlobal(QtCore.QPoint(17, 17)))
wait(20)
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F6))
assert w.isVisible() and w.pie.name == "Sub", (w.isVisible(), w.pie.name)
assert any(not b.isHidden() for b in w.buttons), "sub-pie buttons invisible"
assert rt.dispatcher.current is w        # still tracked for the next key
assert gui.ran == []                     # a descend runs nothing
w.close()
print("PASS door via keys")

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("RUNTIME-TESTS-PASS")
