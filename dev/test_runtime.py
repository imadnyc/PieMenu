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

fired.clear()                        # sticky: fire and stay open (Shift)
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.activate("Std_Undo", sticky=True)
assert fired == ["Std_Undo"] and w.isVisible()
w.activate("Std_Undo", sticky=False)
assert fired == ["Std_Undo", "Std_Undo"] and not w.isVisible()
w.deleteLater()

fired.clear()
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.buttons[2].click()                                 # the door
assert w.pie.name == "Sub" and fired == []           # descended, nothing ran
assert w.isVisible()
assert w._name_label.text() == "Sub"                 # the centre says so
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

# ---- gesture aiming: angular on circles ------------------------------------
import math

w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
og = w.mapToGlobal(QtCore.QPoint(int(w._origin[0]), int(w._origin[1])))


def ray(deg, reach=200):
    a = math.radians(deg)
    return og + QtCore.QPoint(int(math.cos(a) * reach),
                              int(math.sin(a) * reach))


centre = w.buttons[1].mapToGlobal(QtCore.QPoint(17, 17))
assert w.nearest_slot(centre) is w.buttons[1]
# scale independence: the same direction resolves the same at any reach
delta = centre - og
assert w.nearest_slot(og + delta * 30) is w.buttons[1]
# an empty sector (west: slot 6 is unfilled; slot 0 faces north) is a
# no-op target, not a snap to the neighbour
empty = w.nearest_slot(ray(180))
assert empty is w.buttons[6] and not empty.isEnabled()
# ~5 degrees of stickiness: the incumbent keeps the boundary (slot 0 at
# -90°, slot 1 at -45°, boundary -67.5°)
w._aim_stick = None
assert w.nearest_slot(ray(-80)) is w.buttons[0]
assert w.nearest_slot(ray(-66)) is w.buttons[0]  # 1.5° past, held
assert w.nearest_slot(ray(-55)) is w.buttons[1]  # decisively past
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

# ---- a dead slot under the aim is a no-op, not the neighbour ---------------
fired.clear()
pies["Main"].run_on = "release"
w = runtime.PieWidget(pies, "Main", {"Face": 2}, fire)   # Groove goes dead
w.popup_at(QtCore.QPoint(400, 400))
assert not w.buttons[3].isEnabled()
dead_at = w.buttons[3].mapToGlobal(QtCore.QPoint(17, 17))
assert w.nearest_slot(dead_at) is w.buttons[3]   # the dead slot itself
w.commit_gesture(pos=dead_at)
assert fired == [] and not w.isVisible(), fired  # ran nothing, closed
w.deleteLater()
pies["Main"].run_on = "click"
print("PASS dead slot no-op")

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

pies["Main"].shape = "square"            # shape and style hit the stylesheet
pies["Main"].style = "gradient"
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
assert "border-radius:0px" in w.styleSheet()
assert "qlineargradient" in w.styleSheet()
w.deleteLater()
pies["Main"].shape = "circle"
pies["Main"].style = "outline"
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
assert f"border-radius:{pies['Main'].button // 2}px" in w.styleSheet()
assert "background:transparent" in w.styleSheet()
w.deleteLater()
pies["Main"].shape = "rounded"
pies["Main"].style = "flat"

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

# color overrides: params win, empty follows the theme
P = App.ParamGet(runtime.MAIN)
P.SetString("OutlineColor", "#ff0000")
P.SetString("ArrowColor", "#00ff00")
assert runtime.custom_color("OutlineColor").name() == "#ff0000"
assert runtime.arrow_color().name() == "#00ff00"
cw = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
assert "#ff0000" in cw.styleSheet()
cw.deleteLater()
P.RemString("OutlineColor")
P.RemString("ArrowColor")
assert runtime.custom_color("OutlineColor") is None
assert runtime.arrow_color().name() == runtime.accent().name()

# ---- availability (headless: permissive for commands, exact for macros) -----
assert runtime.prefix_available("Std")
assert runtime.prefix_available("")                   # degenerate
assert runtime.prefix_available("NoSuchBenchXYZ")     # headless says yes
assert runtime.command_available("PieMenu_Anything")  # doors always pass
assert runtime.command_available("Weird")             # no underscore, no wb
macro_dir = App.getUserMacroDir(True)
probe = os.path.join(macro_dir, "avail-probe.FCMacro")
with open(probe, "w") as fh:
    fh.write("pass\n")
assert runtime.command_available("Macro:avail-probe.FCMacro")
os.unlink(probe)
assert not runtime.command_available("Macro:definitely-absent.FCMacro")
print("PASS availability")
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


def opener(name, at=None, hint="", mode=None):
    fw = FakeWidget(FakePie(name, run_of[name]))
    fw.at = at
    fw.hint = hint
    fw.mode = mode
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

opened.clear()                       # a stroke finished inside the defer
gmaps["F6"] = {"press": "Main", "double": "Sub"}   # window fires BLIND:
run_of["Main"] = "release"           # mark-ahead, nothing ever renders
blinds = []
disp.blind = lambda name, at, rel: (blinds.append((name, at)), True)[1]
disp.close()
disp.last_tap.clear()
QtGui.QCursor.setPos(QtCore.QPoint(300, 300))
press(disp)
assert opened == []                  # deferred
QtGui.QCursor.setPos(QtCore.QPoint(340, 300))      # 40px: a stroke
release(disp)
assert opened == [] and blinds == [("Main", QtCore.QPoint(300, 300))]
disp.blind = None
wait(400)

opened.clear()                       # held past the defer with motion:
disp.close()                         # the pie appears at the timer,
disp.last_tap.clear()                # anchored at the press
QtGui.QCursor.setPos(QtCore.QPoint(300, 300))
press(disp)
QtGui.QCursor.setPos(QtCore.QPoint(340, 300))
wait(320)
assert [w.pie.name for w in opened] == ["Main"] and opened[0].visible
assert opened[0].at == QtCore.QPoint(300, 300)
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

    def doCommand(self, code):
        self.ran.append(("py", code))

    def listWorkbenches(self):
        return {"PartDesignWorkbench": object()}

    def activateWorkbench(self, name):
        self.ran.append(("wb", name))


App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
for pie in make_pies().values():
    model.save_pie(pie)
model.set_bind(model.ANY_SCOPE, "F6", "Main")
model.set_bind("PartDesign", "F7", "Sub")
model.set_bind(model.ANY_SCOPE, "F8", "Main")

gui = FakeGui()
rt = runtime.Runtime(gui)
rt.reload()
assert set(gui.commands) == {"PieMenu_Main", "PieMenu_Sub",
                             "PieMenu_Smart"}
assert rt._resolve("F6") == "Main"
assert rt._resolve("F7") == "Sub"                    # workbench scope
assert rt._resolve(None) == "Main"                   # right-click: lowest key
assert rt.counts() == {}                             # no Selection on the fake
widget = rt.open_pie("Main")
assert widget is not None and widget.isVisible()
rt.fire("Std_Undo")
assert gui.ran == ["Std_Undo"]
assert model.stats("PartDesign").get("Std_Undo") == 1   # fires are counted
rt.fire("Macro:probe.FCMacro")
assert gui.ran[-1][0] == "py" and "probe.FCMacro" in gui.ran[-1][1]
rt.fire("PartDesignWorkbench")           # workbench entries activate
assert gui.ran[-1] == ("wb", "PartDesignWorkbench")
smart_widget = rt.open_pie(model.SMART_NAME)            # built from stats
assert smart_widget is not None and smart_widget.isVisible()
assert any("Undo" in b.toolTip() for b in smart_widget.buttons
           if not b.isHidden())
smart_widget.close()
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

# ---- the spare mouse buttons dispatch like keys ----------------------------
def mouse_event(kind, button):
    return QtGui.QMouseEvent(kind, QtCore.QPointF(0, 0),
                             QtCore.QPointF(0, 0), button, button,
                             QtCore.Qt.NoModifier)


model.set_bind(model.ANY_SCOPE, "Mouse4", "Main")
rt.reload()
assert rt.dispatcher.eventFilter(
    None, mouse_event(QtCore.QEvent.MouseButtonPress, QtCore.Qt.XButton1))
mw_pie = rt.dispatcher.current
assert mw_pie is not None and mw_pie.isVisible() \
    and mw_pie.pie.name == "Main"
assert rt.dispatcher.eventFilter(
    None, mouse_event(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.XButton1))
assert mw_pie.isVisible()                # a click pie stays for the mouse
assert rt.dispatcher.eventFilter(       # pressing again toggles it shut
    None, mouse_event(QtCore.QEvent.MouseButtonPress, QtCore.Qt.XButton1))
assert rt.dispatcher.current is None \
    or not rt.dispatcher.current.isVisible()
rt.dispatcher.eventFilter(
    None, mouse_event(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.XButton1))
# an unbound thumb button is left alone entirely
assert not rt.dispatcher.eventFilter(
    None, mouse_event(QtCore.QEvent.MouseButtonPress, QtCore.Qt.XButton2))
model.remove_key("Mouse4")
rt.reload()
print("PASS mouse buttons")

# ---- the chooser dismisses itself once the cursor has left -----------------
w = runtime.PieWidget(pies, "Main", {}, fire)
w.popup_at(QtCore.QPoint(400, 400))
live2 = model.live_bindings(pies["Main"].items[4], {})
w.show_chooser(w.buttons[4], live2)
assert w._chooser is not None
QtGui.QCursor.setPos(w._chooser.mapToGlobal(          # parked on it: stays
    w._chooser.rect().center()))
wait(600)
assert w._chooser is not None
QtGui.QCursor.setPos(w.mapToGlobal(QtCore.QPoint(-500, -500)))
wait(1200)                                            # left it: timed out
assert w._chooser is None
w.close()
w.deleteLater()
print("PASS chooser timeout")

# ---- a hold always opens a marking menu ------------------------------------
model.set_bind(model.ANY_SCOPE, "F11", "Sub", "hold")
rt.reload()
QtGui.QCursor.setPos(QtCore.QPoint(500, 500))
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F11))
wait(300)                                    # defer expires, pie opens
held_w = rt.dispatcher.current
assert held_w is not None and held_w.run_mode == "release"
assert held_w.pie.name == "Sub"              # Sub's own run_on is click
rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F11))
assert rt.dispatcher.current is None         # dead-zone release: closed
wait(400)
print("PASS hold is marking")

# ---- mark-ahead: a fast flick fires blind ----------------------------------
gui.ran.clear()
P0 = QtCore.QPoint(600, 500)
QtGui.QCursor.setPos(P0)
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F11))
QtGui.QCursor.setPos(P0 + QtCore.QPoint(150, 0))     # flick east: Redo
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F11))
assert gui.ran == ["Std_Redo"], gui.ran
assert rt.dispatcher.current is None                 # never rendered
assert any("mark-ahead" in line for line in rt.dispatcher.trace)
wait(400)
# a flick at a dead sector cannot fire: the pie appears as the fallback
gui.ran.clear()
QtGui.QCursor.setPos(P0)
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F11))
QtGui.QCursor.setPos(P0 + QtCore.QPoint(0, -150))    # north: dead slot
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F11))
assert gui.ran == []
fallback_w = rt.dispatcher.current
assert fallback_w is not None and fallback_w.isVisible()
fallback_w.close()
rt.dispatcher.current = None
wait(400)
print("PASS mark-ahead")

# ---- devices that never send key-up ----------------------------------------
rt.dispatcher._stuck.setInterval(400)
QtGui.QCursor.setPos(QtCore.QPoint(700, 500))
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F11))
wait(1400)     # opens at 170ms; the warp counts as one tick of motion,
stuck_w = rt.dispatcher.current              # the next tick demotes
assert stuck_w is not None and stuck_w.isVisible()
assert stuck_w.run_mode == "click"           # demoted: stays for the mouse
assert rt.dispatcher.held is None
stuck_w.close()
rt.dispatcher.current = None
rt.dispatcher._stuck.setInterval(rt.dispatcher.STUCK_MS)
model.remove_key("F11")
rt.reload()
wait(400)
print("PASS key-up timeout")

# ---- letter accels fire their slot -----------------------------------------
pies["Main"].items[1] = [Binding("Std_Undo", accel="U")]
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
fired.clear()
w.keyPressEvent(QtGui.QKeyEvent(
    QtCore.QEvent.KeyPress, QtCore.Qt.Key_U, QtCore.Qt.NoModifier, "u"))
assert fired == ["Std_Undo"], fired
assert not w.isVisible()
w.deleteLater()
pies["Main"].items[1] = [Binding("Std_Undo")]
print("PASS letter accels")

# ---- light and dark themes, and the style presets --------------------------
pth = App.ParamGet("User parameter:BaseApp/PieMenu")
pth.SetString("Theme", "dark")
w = runtime.PieWidget(pies, "Main", {}, fire)
assert runtime.THEMES["dark"]["fill"] in w._base_css
assert runtime.THEMES["dark"]["text"] in w._base_css
w.deleteLater()
pth.SetString("Theme", "light")
w = runtime.PieWidget(pies, "Main", {}, fire)
assert runtime.THEMES["light"]["fill"] in w._base_css
w.deleteLater()
pth.SetString("FillColor", "#123456")    # explicit override beats theme
w = runtime.PieWidget(pies, "Main", {}, fire)
assert "#123456" in w._base_css
w.deleteLater()
pth.RemString("FillColor")
pth.RemString("Theme")
for style_name, needle in (("soft", "border:none"),
                           ("glass", "rgba("),
                           ("bold", "border:2px solid"),
                           ("minimal", "background:transparent")):
    pies["Main"].style = style_name
    w = runtime.PieWidget(pies, "Main", {}, fire)
    assert needle in w._base_css, (style_name, w._base_css)
    w.grab()
    w.deleteLater()
pies["Main"].style = "flat"
print("PASS themes and styles")

# ---- the opaque fallback paints without crashing ----------------------------
App.ParamGet("User parameter:BaseApp/PieMenu").SetBool("OpaquePies", True)
w = runtime.PieWidget(pies, "Main", {}, fire)
w.popup_at(QtCore.QPoint(400, 400))
assert w._opaque
w.grab()                                     # exercises the paint path
w.close()
w.deleteLater()
App.ParamGet("User parameter:BaseApp/PieMenu").RemBool("OpaquePies")
print("PASS opaque fallback")

# ---- Run: binds fire one command, no pie -----------------------------------
model.set_bind(model.ANY_SCOPE, "F10", "Run:Std_New")
rt.reload()
gui.ran.clear()
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F10))
assert gui.ran == ["Std_New"]                # fired on the press itself
assert rt.dispatcher.current is None         # and no widget opened
rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F10))
wait(400)                                    # clear the double window
# tap = the command, hold = a pie, on the same key
model.set_bind(model.ANY_SCOPE, "F10", "Sub", "hold")
rt.reload()
gui.ran.clear()
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F10))
assert gui.ran == []                         # ambiguous: deferred
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F10))
assert gui.ran == ["Std_New"]                # early release = the tap
wait(400)
gui.ran.clear()
assert rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_F10))
wait(300)                                    # past DEFER_MS: the hold
held_pie = rt.dispatcher.current
assert held_pie is not None and held_pie.pie.name == "Sub"
assert gui.ran == []
rt.dispatcher.eventFilter(
    None, key_event(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_F10))
rt.dispatcher.close()
model.remove_key("F10")
rt.reload()
print("PASS run binds")

# ---- a release that resolves nowhere runs nothing --------------------------
fired.clear()
gfar = Pie("GFar", family="grid", cols=4, rows=1, radius=80,
           run_on="release")
model.normalise(gfar)
gfar.items[0] = [Binding("Std_Undo")]
w = runtime.PieWidget({"GFar": gfar}, "GFar", {}, fire)
w.popup_at(QtCore.QPoint(400, 400))
w.commit_gesture(pos=w.mapToGlobal(QtCore.QPoint(-3000, -3000)))
assert fired == [] and not w.isVisible()     # far off a grid: abort
w.deleteLater()
print("PASS far release aborts")

# ---- aim feedback: highlight ring and centre readout -----------------------
pies["Main"].run_on = "release"
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(400, 400))
over = w.buttons[1].mapToGlobal(QtCore.QPoint(17, 17))
w.mouseMoveEvent(QtGui.QMouseEvent(
    QtCore.QEvent.MouseMove, QtCore.QPointF(w.mapFromGlobal(over)),
    QtCore.QPointF(over), QtCore.Qt.NoButton, QtCore.Qt.NoButton,
    QtCore.Qt.NoModifier))
assert w._aimed is w.buttons[1]
assert w.buttons[1].property("aimed") is True
assert w._name_label.text() == w.buttons[1].property("aimname")
west = QtCore.QPoint(int(w._origin[0]) - 200, int(w._origin[1]))
w.mouseMoveEvent(QtGui.QMouseEvent(
    QtCore.QEvent.MouseMove, QtCore.QPointF(west),
    QtCore.QPointF(w.mapToGlobal(west)), QtCore.Qt.NoButton,
    QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
assert w._name_label.text() == "—"           # empty sector, not "Cancel"
inside = QtCore.QPoint(int(w._origin[0]) + 2, int(w._origin[1]) + 2)
w.mouseMoveEvent(QtGui.QMouseEvent(
    QtCore.QEvent.MouseMove, QtCore.QPointF(inside),
    QtCore.QPointF(w.mapToGlobal(inside)), QtCore.Qt.NoButton,
    QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
assert w._aimed is None and not w.buttons[1].property("aimed")
assert w._name_label.text() == "Cancel"      # the dead zone is legible
w.close()
w.deleteLater()
pies["Main"].run_on = "click"
print("PASS aim feedback")

# ---- a pie at the screen corner shifts fully on-screen ---------------------
w = runtime.PieWidget(pies, "Main", {"Face": 1}, fire)
w.popup_at(QtCore.QPoint(2, 2))
avail = QtWidgets.QApplication.primaryScreen().availableGeometry()
assert w.x() >= avail.left() and w.y() >= avail.top()
w.close()
w.deleteLater()
print("PASS screen clamp")

# ---- availability caches: yes sticks until reload --------------------------
runtime._AVAILABLE["prefix"].clear()
assert runtime.prefix_available("PartDesign")
assert "PartDesign" in runtime._AVAILABLE["prefix"]
rt.reload()
assert not runtime._AVAILABLE["prefix"]
print("PASS availability cache")

# ---- task panel slots ------------------------------------------------------
holder = QtWidgets.QWidget()
panel_box = QtWidgets.QDialogButtonBox(
    QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
    holder)
holder.show()
panel_clicks = []
panel_box.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(
    lambda: panel_clicks.append("ok"))


class PanelGui(FakeGui):
    def getMainWindow(self):
        return holder


prt = runtime.Runtime(PanelGui())
prt.fire("Panel:OK")
assert panel_clicks == ["ok"]
prt.fire("Panel:Apply")                      # no Apply button: quiet no-op
assert panel_clicks == ["ok"]
holder.close()
assert runtime.command_available("Panel:OK")
# headless there is no task panel, so the slot renders dead with a reason
ppie = Pie("PanelPie", slots=2, per_ring=2)
model.normalise(ppie)
ppie.items[0] = [Binding("Panel:OK")]
pw2 = runtime.PieWidget({"PanelPie": ppie}, "PanelPie", {}, fire)
assert not pw2.buttons[0].isEnabled()
assert "no task panel open" in pw2.buttons[0].toolTip()
pw2.deleteLater()
print("PASS task panel slots")

# ---- pinned palette: edge snap + tuck-away ---------------------------------
host = QtWidgets.QWidget()
host.resize(800, 600)
host.show()


class MwGui(FakeGui):
    def getMainWindow(self):
        return host


prt2 = runtime.Runtime(MwGui())
prt2.reload()
pal = prt2.pin_pie("Main")
assert pal.parentWidget() is host
pal.move(5, 200)                             # dropped near the left edge
pal._drag_at = QtCore.QPoint(1, 1)
pal.mouseReleaseEvent(QtGui.QMouseEvent(
    QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(1, 1),
    QtCore.QPointF(6, 201), QtCore.Qt.LeftButton, QtCore.Qt.NoButton,
    QtCore.Qt.NoModifier))
assert pal._snapped_edge == "left" and pal.x() == 2
pal._collapse()                              # mouse-leave folds to a tab
assert pal._collapsed and pal.width() == 14
assert all(c.isHidden() for c in pal.findChildren(QtWidgets.QWidget))
pal._expand()                                # hover reopens
assert not pal._collapsed
assert any(not b.isHidden() for b in pal.buttons)
pal.close()
host.close()
print("PASS palette snap")

# ---- last fired wears the ring at the next open ----------------------------
lf = rt.open_pie("Main")
lf.activate("Std_Undo", sticky=True)     # fires without closing
lf.close()
assert model.last_fired("Main") == "Std_Undo"
lf = rt.open_pie("Main")
marked = [b for b in lf.buttons if b.property("last")]
assert len(marked) == 1 and "Undo" in marked[0].toolTip()
lf.close()
print("PASS last-fired ring")

# ---- pinned palettes -------------------------------------------------------
gui.ran.clear()
pw = rt.pin_pie("Main")
assert pw is not None and pw.pinned and pw.isVisible()
assert isinstance(pw._name_label, runtime.HaloLabel)  # outlined text
assert pw in rt._pinned
pw.activate("Std_Undo")                  # fires without closing
assert gui.ran == ["Std_Undo"] and pw.isVisible()
pw.activate("PieMenu_Sub")               # doors re-anchor in place
assert pw.pie.name == "Sub" and pw.isVisible() and pw.pinned
pw.refresh_counts({"Face": 1})           # selection change rebuilds
assert pw.isVisible() and pw.pinned
rt._selection_settled()                  # the runtime refresh path
assert pw.isVisible()
pw.close()
assert pw not in rt._pinned
print("PASS pinned palettes")

# P on an open popup closes it and spawns a separate born-pinned palette
# (never re-flags the live window: that crashes under Wayland)
w2 = rt.open_pie("Main")
rt.dispatcher.current = w2
w2.keyPressEvent(key_event(QtCore.QEvent.KeyPress, QtCore.Qt.Key_P))
assert not w2.isVisible()
palette = rt._pinned[-1]
assert palette is not w2 and palette.pinned and palette.isVisible()
palette.close()
assert palette not in rt._pinned
print("PASS key P spawns a palette")

# ---- sketch-edit scope -----------------------------------------------------
class FakeSketch:
    def isDerivedFrom(self, t):
        return t == "Sketcher::SketchObject"


class FakeEdit:
    Object = FakeSketch()


class FakeEditDoc:
    def getInEdit(self):
        return FakeEdit()


assert runtime.workbench_scope(gui) == "PartDesign"
gui.ActiveDocument = FakeEditDoc()
assert runtime.workbench_scope(gui) == model.SKETCH_EDIT_SCOPE
# resolution chains SketchEdit -> Sketcher -> Any
model.set_bind("Sketcher", "F6", "Sub")
rt.reload()
assert rt._resolve("F6") == "Sub"        # Sketcher bind wins over Any's Main
model.set_bind(model.SKETCH_EDIT_SCOPE, "F6", "Main")
rt.reload()
assert rt._resolve("F6") == "Main"       # the edit-scope bind wins over both
gui.ActiveDocument = None
print("PASS sketch-edit scope")

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("RUNTIME-TESTS-PASS")
