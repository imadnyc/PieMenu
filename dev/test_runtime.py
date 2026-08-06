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
centre = w.mapToGlobal(QtCore.QPoint(int(w._origin[0]), int(w._origin[1])))
w.commit_gesture(pos=centre)             # released from the dead-zone
assert fired == [] and not w.isVisible() # no aim: vanish, fire nothing
w.deleteLater()

fired.clear()
w = runtime.PieWidget(pies, "Main", {}, fire)
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

# ---- doors on hover, chooser size ------------------------------------------
fired.clear()
pies["Main"].run_on = "release"
pies["Main"].delay = 200
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
app.sendEvent(w.buttons[2], QtCore.QEvent(QtCore.QEvent.Enter))
ring = w.buttons[2].findChild(runtime._DwellRing)
assert ring is not None and ring.isVisible()   # armed the moment we enter
for _ in range(40):                      # the ring fills (deadline, not race)
    if ring.progress > 0:
        break
    wait(25)
assert 0 < ring.progress <= 1
for _ in range(40):                      # then the dwell opens the door
    if w.pie.name == "Sub":
        break
    wait(50)
assert w.pie.name == "Sub" and fired == [], (w.pie.name, fired)
assert any(not b.isHidden() for b in w.buttons)
# Sub is a click pie, but it was entered mid-gesture: release still fires
assert w.run_mode == "release"
w.commit_gesture(pos=w.buttons[1].mapToGlobal(QtCore.QPoint(17, 17)))
assert fired == ["Std_Redo"], fired
assert not w.isVisible()
w.deleteLater()

pies["Main"].door_hover = False          # knob off: dwelling stays put
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
app.sendEvent(w.buttons[2], QtCore.QEvent(QtCore.QEvent.Enter))
wait(150)
assert w.pie.name == "Main"
w.close()
w.deleteLater()
pies["Main"].door_hover = True
pies["Main"].run_on = "click"

pies["Main"].alt_size = 40
w = runtime.PieWidget(pies, "Main", {}, fire)
w.show_chooser(w.buttons[4], model.live_bindings(pies["Main"].items[4], {}))
alts = w._chooser.findChildren(QtWidgets.QToolButton)
assert alts and alts[0].width() == 40    # the chooser-size knob
assert w.buttons[1].property("alt") is True      # odd slots alternate fill
assert not w.buttons[0].property("alt")
w.deleteLater()

pies["Main"].show_names = True           # names need room, buttons grow
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
assert w.buttons[1].text() == "Undo"
assert w.buttons[1].height() > pies["Main"].button
long_pie = Pie("Long", slots=2, per_ring=2, show_names=True)
model.normalise(long_pie)
long_pie.items[0] = [Binding("Sketcher_ConstrainPerpendicular")]
lw = runtime.PieWidget({"Long": long_pie}, "Long", {}, fire)
hint = lw.buttons[0].sizeHint()
assert lw.buttons[0].width() >= hint.width()      # style says it fits
assert lw.buttons[0].height() >= hint.height()
lw.deleteLater()

# colour overrides: params win, empty follows the theme
P = App.ParamGet(runtime.MAIN)
P.SetString("OutlineColor", "#ff0000")
P.SetString("ArrowColor", "#00ff00")
assert runtime.custom_colour("OutlineColor").name() == "#ff0000"
assert runtime.arrow_colour().name() == "#00ff00"
cw = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
assert "#ff0000" in cw.styleSheet()
cw.deleteLater()
P.RemString("OutlineColor")
P.RemString("ArrowColor")
assert runtime.custom_colour("OutlineColor") is None
assert runtime.arrow_colour().name() == runtime.accent().name()
shown = [b.geometry() for b in w.buttons if not b.isHidden()]
for i, r1 in enumerate(shown):           # ...and the layout spreads so no
    for r2 in shown[i + 1:]:             # name is covered by a neighbour
        assert not r1.intersects(r2), (r1, r2)
w.deleteLater()
pies["Main"].show_names = False
pies["Main"].alt_size = 24
pies["Main"].delay = 250
pies["Main"].last_used.clear()
print("PASS door hover + chooser size")


# ---- dispatcher: press and double-press; release is the pie's run_on --------
class FakePie:
    def __init__(self, name, run_on):
        self.name, self.run_on = name, run_on


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
gmaps = {"F6": {"press": "Main"}}
run_of = {"Main": "click", "Sub": "click"}


def opener(name, at=None):
    fw = FakeWidget(FakePie(name, run_of[name]))
    fw.at = at
    opened.append(fw)
    return fw


def press(disp, key=QtCore.Qt.Key_F6):
    return disp.eventFilter(None, key_event(QtCore.QEvent.KeyPress, key))


def release(disp, key=QtCore.Qt.Key_F6):
    return disp.eventFilter(None, key_event(QtCore.QEvent.KeyRelease, key))


disp = runtime.Dispatcher(opener, lambda k: dict(gmaps.get(k, {})),
                          mode_of=lambda n: run_of[n])

# a persistent pie: press opens, release leaves it up, press again toggles
App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", True)
assert press(disp)
assert len(opened) == 1 and opened[0].visible
assert release(disp)
assert opened[0].visible and not opened[0].committed
press(disp)
assert len(opened) == 1 and not opened[0].visible    # toggled shut

App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", False)
press(disp)
press(disp)                          # second press keeps the open pie as-is
assert len(opened) == 2 and opened[1].visible
App.ParamGet(runtime.MAIN).SetBool("GlobalKeyToggle", True)

opened.clear()                       # a gesture pie: press opens NOW,
gmaps["F6"] = {"press": "Main"}      # release commits the aim
run_of["Main"] = "release"
disp.close()
disp.last_tap.clear()
press(disp)
assert len(opened) == 1 and opened[0].visible
release(disp)
assert opened[0].committed

opened.clear()                       # gesture pie + double: press DEFERS,
gmaps["F6"] = {"press": "Main", "double": "Sub"}   # a quick tap is a no-op
disp.close()
disp.last_tap.clear()
press(disp)
assert opened == []                  # nothing shown yet
release(disp)
assert opened == []                  # pure tap: nothing at all
press(disp)                          # second press within the window
assert [w.pie.name for w in opened] == ["Sub"]     # the double, no flicker
assert opened[0].visible
release(disp)
assert opened[0].visible             # Sub is a click pie: it stays

opened.clear()                       # held past the defer: the gesture pie
disp.close()                         # appears mid-hold
disp.last_tap.clear()
press(disp)
assert opened == []
wait(320)                            # defer timer fires while held
assert [w.pie.name for w in opened] == ["Main"] and opened[0].visible
assert disp.held is not None
release(disp)
assert opened[0].committed           # and release commits as usual

opened.clear()                       # moving the mouse cuts the wait short:
gmaps["F6"] = {"press": "Main", "double": "Sub"}   # gesturing, not tapping
run_of["Main"] = "release"
disp.close()
disp.last_tap.clear()
QtGui.QCursor.setPos(QtCore.QPoint(300, 300))
press(disp)
assert opened == []                  # deferred
QtGui.QCursor.setPos(QtCore.QPoint(340, 300))      # 40px: clearly a gesture
move = QtGui.QMouseEvent(QtCore.QEvent.MouseMove,
                         QtCore.QPointF(0, 0), QtCore.QPointF(340, 300),
                         QtCore.Qt.NoButton, QtCore.Qt.NoButton,
                         QtCore.Qt.NoModifier)
disp.eventFilter(None, move)
assert [w.pie.name for w in opened] == ["Main"] and opened[0].visible
assert opened[0].at == QtCore.QPoint(300, 300)     # anchored at the press
assert disp.held is not None
release(disp)
assert opened[0].committed

opened.clear()                       # only a double bound: first press arms
gmaps["F6"] = {"double": "Sub"}
run_of["Main"] = "click"
disp.close()
disp.last_tap.clear()
press(disp)
assert opened == []
press(disp)
assert [w.pie.name for w in opened] == ["Sub"]

opened.clear()                       # press vs hold: tap gets the press pie
gmaps["F6"] = {"press": "Sub", "hold": "Main"}
run_of["Main"] = "release"
disp.close()
disp.last_tap.clear()
press(disp)
assert opened == []                  # ambiguous: deferred
release(disp)                        # a tap: the persistent press pie
assert [w.pie.name for w in opened] == ["Sub"] and opened[0].visible

opened.clear()                       # ...and holding gets the hold pie
disp.close()
disp.last_tap.clear()
wait(400)                            # let the double window lapse
press(disp)
assert opened == []
wait(320)                            # defer elapses while held
assert [w.pie.name for w in opened] == ["Main"] and opened[0].visible
release(disp)
assert opened[0].committed

opened.clear()                       # double vs double-hold on one key
gmaps["F6"] = {"double": "Sub", "double-hold": "Main"}
disp.close()
disp.last_tap.clear()
press(disp)
release(disp)                        # first tap arms
press(disp)                          # second press: ambiguous pair
assert opened == []
release(disp)                        # released quickly: the double-tap
assert [w.pie.name for w in opened] == ["Sub"] and opened[0].visible

opened.clear()
disp.close()
disp.last_tap.clear()
wait(400)
press(disp)
release(disp)
press(disp)                          # tap, then press-and-hold
wait(320)
assert [w.pie.name for w in opened] == ["Main"] and opened[0].visible
release(disp)
assert opened[0].committed           # the double-hold gestured
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
model.set_bind(model.ANY_SCOPE, "F8", "Main")

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
# F8 presses into Main, a release-mode pie: press opens, release commits
rt.pies["Main"].run_on = "release"
gui.ran.clear()
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F8))
w = rt.dispatcher.current
assert w is not None and w.isVisible() and w.pie.name == "Main"
QtGui.QCursor.setPos(w.buttons[2].mapToGlobal(QtCore.QPoint(17, 17)))
wait(20)
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F8))
assert w.isVisible() and w.pie.name == "Sub", (w.isVisible(), w.pie.name)
assert any(not b.isHidden() for b in w.buttons), "sub-pie buttons invisible"
assert rt.dispatcher.current is w        # still tracked for the next key
assert gui.ran == []                     # a descend runs nothing
w.close()
print("PASS door via keys")

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("RUNTIME-TESTS-PASS")
