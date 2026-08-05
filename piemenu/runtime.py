"""The v2 runtime: live pies, resolution, dispatch.

Renders pies from the v2 model, resolves each slot against the current
selection counts (first match wins, several matches offer the chooser),
treats ``PieMenu_<name>`` bindings as doors that open that pie at the same
cursor position, and dispatches workbench-scoped shortcuts through the one
rule: a workbench binding beats the Any scope.

Structured for testability: the widget and the dispatcher take their inputs
(pies, counts, fire) as callables, so the headless tests drive them without a
FreeCAD GUI; ``start()`` wires the real thing.
"""

import os

from PySide import QtCore, QtGui, QtWidgets

try:
    import FreeCAD as App
except ImportError:
    App = None

from . import model, resources
from .model import is_pie_command, pie_target

MAIN = "User parameter:BaseApp/PieMenu"
LOGO = os.path.join(resources.respath, "PieMenu_Logo.svg")

runtime = None      # the singleton, created by start()


def _param():
    return App.ParamGet(MAIN)


def behaviour():
    p = _param()
    return {
        "quick": p.GetBool("ShowQuickMenu", True),
        "toggle": p.GetBool("GlobalKeyToggle", True),
        "rclick": p.GetBool("RightClickTrigger", False),
        "rclick_delay": p.GetInt("DelayRightClick", 0) or 350,
    }


def workbench_scope(gui):
    """The active workbench as a scope name ("PartDesign")."""
    try:
        return gui.activeWorkbench().name().split("Workbench")[0]
    except Exception:  # noqa: BLE001 -- half-built Gui in console mode
        return ""


def selection_counts(gui):
    """The selection as counts per axis, the shape every rule matches against.

    Ported from the v1 listTopo/selectionCounts split; datum objects map onto
    the Vertex/Axis/Plane axes exactly as before.
    """
    counts = dict.fromkeys(model.AXES, 0)
    try:
        selection = gui.Selection.getSelectionEx()
    except Exception:  # noqa: BLE001 -- no Selection in console mode
        return {}
    axis_names = ("X_Axis", "Y_Axis", "Z_Axis", "H_Axis", "V_Axis")
    plane_names = ("XY_Plane", "XZ_Plane", "YZ_Plane")
    subs = []
    for sel in selection:
        name = sel.ObjectName
        if name in axis_names or name in plane_names:
            subs.append(name)
        elif name.startswith("DatumPlane"):
            counts["Plane"] += 1
        elif name.startswith("DatumLine"):
            counts["Axis"] += 1
        elif name.startswith("DatumPoint"):
            counts["Vertex"] += 1
        elif not sel.SubElementNames:
            counts["Object"] += 1
        else:
            subs.extend(sel.SubElementNames)
    for sub in subs:
        if sub.startswith(("Vertex", "ExternalVertex", "RootPoint")):
            counts["Vertex"] += 1
        elif sub.startswith(("Edge", "ExternalEdge")):
            counts["Edge"] += 1
        elif sub.startswith("Face"):
            counts["Face"] += 1
        elif sub.startswith(axis_names):
            counts["Axis"] += 1
        elif sub.startswith(plane_names):
            counts["Plane"] += 1
    return {k: v for k, v in counts.items() if v}


def command_action(name):
    """The main window QAction registered for a command, or None.

    FreeCAD names every command's action after the command, which is also how
    the v1 code found its icons.
    """
    if App is None or not App.GuiUp:
        return None
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    if mw is None:
        return None
    return mw.findChild(QtGui.QAction, name)


# ---- the pie widget --------------------------------------------------------

class PieWidget(QtWidgets.QWidget):
    """One open pie: buttons at model.positions, resolved against counts.

    fire(cmd) runs a command; doors are handled here (open the target pie in
    place) so fire only ever sees runnable commands.
    """

    def __init__(self, pies, name, counts, fire, quick_menu=None, parent=None):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.pies = pies
        self.counts = counts
        self.fire = fire
        self.quick_menu = quick_menu
        self._hover_timer = None
        self._chooser = None
        self.build(name)

    # -- construction

    def build(self, name):
        for child in self.findChildren(QtWidgets.QWidget):
            child.deleteLater()
        self._chooser = None
        pie = self.pies[name]
        model.normalise(pie)
        self.pie = pie
        pos = model.positions(pie)
        size = pie.button
        pad = 24
        min_x = min(x for x, _ in pos) - size / 2 - pad
        max_x = max(x for x, _ in pos) + size / 2 + pad
        min_y = min(y for _, y in pos) - size / 2 - pad
        max_y = max(y for _, y in pos) + size / 2 + pad
        # the cursor anchor must sit at (0,0) of the layout
        self._origin = (-min_x, -min_y)
        self.resize(int(max_x - min_x), int(max_y - min_y))

        self.buttons = []
        for i, (x, y) in enumerate(pos):
            btn = self._slot_button(pie.items[i], i)
            btn.move(int(x - min_x - size / 2), int(y - min_y - size / 2))
            self.buttons.append(btn)
        if behaviour_quick(self):
            self._centre_button()

    def _slot_button(self, slot, index):
        pie = self.pie
        btn = QtWidgets.QToolButton(self)
        btn.setFixedSize(pie.button, pie.button)
        btn.setIconSize(QtCore.QSize(int(pie.button * 0.6), int(pie.button * 0.6)))
        live = model.live_bindings(slot, self.counts)
        binding = live[0] if live else (slot[0] if slot else None)
        if binding is None:
            btn.setEnabled(False)
            btn.setVisible(False)
            return btn
        self._decorate(btn, binding, bool(live), len(live))
        if live:
            if len(live) > 1:
                btn.installEventFilter(_ChooserFilter(self, btn, live))
            b = live[0]
            btn.clicked.connect(lambda _=False, cmd=b.cmd: self.activate(cmd))
            if pie.run_on == "hover":
                btn.installEventFilter(_HoverFire(self, btn, b.cmd, pie.delay))
        return btn

    def _decorate(self, btn, binding, live, n_live):
        cmd = binding.cmd
        tip = cmd
        if is_pie_command(cmd):
            target = pie_target(cmd)
            btn.setIcon(QtGui.QIcon(LOGO))
            tip = f"Open {target}"
            dead = not model.pie_live(target, self.pies, self.counts)
            colour = "#808080" if (dead or not live) else "palette(highlight)"
            btn.setStyleSheet(
                f"QToolButton{{border:2px solid {colour};"
                f"border-radius:{self.pie.button // 2}px;}}")
            live = live and not dead
        else:
            action = command_action(cmd)
            if action is not None:
                btn.setIcon(action.icon())
                tip = action.toolTip() or cmd
        if self.pie.show_names:
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            btn.setText(cmd.split("_", 1)[-1])
        if n_live > 1:
            tip += f"  ({n_live} apply — hover to choose)"
        btn.setToolTip(tip)
        btn.setEnabled(bool(live))

    def _centre_button(self):
        pie = self.pie
        size = max(22, int(pie.button * 0.7))
        btn = QtWidgets.QToolButton(self)
        btn.setFixedSize(size, size)
        btn.setIcon(QtGui.QIcon(LOGO))
        btn.setStyleSheet(f"QToolButton{{border-radius:{size // 2}px;}}")
        btn.move(int(self._origin[0] - size / 2), int(self._origin[1] - size / 2))
        btn.setToolTip("QuickMenu")
        if self.quick_menu is not None:
            btn.clicked.connect(lambda: self.quick_menu(self))
        self._centre = btn

    # -- behaviour

    def activate(self, cmd):
        """Run a command, or descend into a pie at the same spot."""
        if is_pie_command(cmd):
            target = pie_target(cmd)
            if target in self.pies:
                anchor = self.mapToGlobal(
                    QtCore.QPoint(int(self._origin[0]), int(self._origin[1])))
                self.build(target)
                self.popup_at(anchor)
                return
        self.close()
        self.fire(cmd)

    def popup_at(self, global_pos):
        self.move(int(global_pos.x() - self._origin[0]),
                  int(global_pos.y() - self._origin[1]))
        self.show()

    def nearest_slot(self, global_pos):
        """The enabled button nearest the cursor, for gesture release."""
        best, dist = None, None
        for btn in self.buttons:
            if not btn.isEnabled() or not btn.isVisible():
                continue
            centre = btn.mapToGlobal(
                QtCore.QPoint(btn.width() // 2, btn.height() // 2))
            d = (centre.x() - global_pos.x()) ** 2 \
                + (centre.y() - global_pos.y()) ** 2
            if dist is None or d < dist:
                best, dist = btn, d
        if best is None:
            return None
        limit = (self.pie.button * 1.6) ** 2
        under = self.rect().contains(self.mapFromGlobal(global_pos))
        return best if (under or dist <= limit * 4) else None

    def commit_gesture(self):
        """Release in a hold pie: run whatever the cursor is aimed at."""
        btn = self.nearest_slot(QtGui.QCursor.pos())
        if btn is not None:
            btn.click()
        else:
            self.close()


def behaviour_quick(_widget):
    try:
        return behaviour()["quick"]
    except Exception:  # noqa: BLE001 -- no params outside FreeCAD
        return True


class _HoverFire(QtCore.QObject):
    """run_on == hover: dwelling on a slot for the delay fires it."""

    def __init__(self, pie_widget, btn, cmd, delay):
        super().__init__(btn)
        self.w, self.cmd = pie_widget, cmd
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(max(50, delay))
        self.timer.timeout.connect(lambda: self.w.activate(self.cmd))

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Enter:
            self.timer.start()
        elif event.type() == QtCore.QEvent.Leave:
            self.timer.stop()
        return False


class _ChooserFilter(QtCore.QObject):
    """Several bindings apply: hovering the slot offers all of them."""

    def __init__(self, pie_widget, btn, bindings):
        super().__init__(btn)
        self.w, self.btn, self.bindings = pie_widget, btn, bindings

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Enter:
            self.w.show_chooser(self.btn, self.bindings)
        return False


def _chooser_widget(pie_widget, btn, bindings):
    box = QtWidgets.QWidget(pie_widget)
    lay = QtWidgets.QHBoxLayout(box)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    for b in bindings:
        alt = QtWidgets.QToolButton(box)
        alt.setIconSize(QtCore.QSize(18, 18))
        pie_widget._decorate(alt, b, True, 1)
        alt.setFixedSize(24, 24)
        alt.clicked.connect(lambda _=False, cmd=b.cmd: pie_widget.activate(cmd))
        lay.addWidget(alt)
    box.adjustSize()
    x = btn.x() + btn.width() // 2 - box.width() // 2
    y = btn.y() + btn.height() + 4
    box.move(max(0, min(x, pie_widget.width() - box.width())), y)
    box.show()
    return box


def _show_chooser(self, btn, bindings):
    if self._chooser is not None:
        self._chooser.deleteLater()
    self._chooser = _chooser_widget(self, btn, bindings)


PieWidget.show_chooser = _show_chooser


# ---- dispatch --------------------------------------------------------------

class Dispatcher(QtCore.QObject):
    """App-wide key handling implementing open_on and the toggles.

    open_on: single (press opens; pressing again closes when the toggle
    behaviour is on), double (two taps within 350ms), hold (opens on press
    and, when run_on is release, releasing fires the aimed slot), double-hold.
    Also the long right-click trigger.
    """

    def __init__(self, opener, resolver, open_on_of=None, parent=None):
        super().__init__(parent)
        self.opener = opener          # opener(pie_name) -> PieWidget|None
        self.resolver = resolver      # resolver(key) -> pie_name|None
        self.open_on_of = open_on_of or (lambda name: "single")
        self.current = None           # the open PieWidget
        self.last_tap = {}            # key -> ms timestamp
        self.held = None              # key currently held for a hold pie
        self._rtimer = None
        self._swallow_context = False

    # -- helpers

    def _key_of(self, event):
        combo = event.keyCombination() if hasattr(event, "keyCombination") \
            else None
        if combo is not None:
            return QtGui.QKeySequence(combo).toString()
        return QtGui.QKeySequence(event.key()).toString()

    def _double(self, key, now):
        last = self.last_tap.get(key, -10**9)
        self.last_tap[key] = now
        return (now - last) < 350

    def open_pie(self, name):
        self.close()
        self.current = self.opener(name)
        return self.current

    def close(self):
        if self.current is not None:
            self.current.close()
            self.current = None
        self.held = None

    # -- the filter

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QtCore.QEvent.KeyPress and not event.isAutoRepeat():
            return self._key_press(event)
        if etype == QtCore.QEvent.KeyRelease and not event.isAutoRepeat():
            return self._key_release(event)
        if App is not None and behaviour()["rclick"]:
            if etype == QtCore.QEvent.MouseButtonPress \
                    and event.button() == QtCore.Qt.RightButton:
                self._arm_rclick()
            elif etype in (QtCore.QEvent.MouseButtonRelease,
                           QtCore.QEvent.MouseMove):
                self._disarm_rclick()
            elif etype == QtCore.QEvent.ContextMenu and self._swallow_context:
                self._swallow_context = False
                return True
        return False

    def _key_press(self, event):
        key = self._key_of(event)
        name = self.resolver(key)
        if not name:
            return False
        open_on = self.open_on_of(name)
        now = _now_ms()
        if open_on in ("double", "double-hold") \
                and not self._double(key, now):
            return True
        if (open_on == "single" and self.current is not None
                and self.current.isVisible() and behaviour()["toggle"]):
            self.close()
            return True
        self.open_pie(name)
        if open_on in ("hold", "double-hold"):
            # after open_pie, which clears any previous hold via close()
            self.held = key
        return True

    def _key_release(self, event):
        if self.held is None:
            return False
        if self._key_of(event) != self.held:
            return False
        self.held = None
        widget = self.current
        if widget is None:
            return False
        if widget.pie.run_on == "release":
            widget.commit_gesture()
        else:
            # a held pie is momentary: letting go closes it
            widget.close()
        self.current = None
        return True

    # -- right click

    def _arm_rclick(self):
        self._disarm_rclick()
        self._rtimer = QtCore.QTimer(self)
        self._rtimer.setSingleShot(True)
        self._rtimer.setInterval(behaviour()["rclick_delay"])
        self._rtimer.timeout.connect(self._rclick_open)
        self._rtimer.start()

    def _disarm_rclick(self):
        if self._rtimer is not None:
            self._rtimer.stop()
            self._rtimer = None

    def _rclick_open(self):
        name = self.resolver(None)
        if name:
            self._swallow_context = True
            self.open_pie(name)


def _now_ms():
    return QtCore.QDateTime.currentMSecsSinceEpoch()


# ---- the FreeCAD-facing runtime -------------------------------------------

class _PieCommand:
    """Every pie is an ordinary command, so slots and toolbars can open it."""

    def __init__(self, name):
        self.name = name

    def GetResources(self):
        return {"Pixmap": LOGO, "MenuText": f"Pie: {self.name}",
                "ToolTip": f"Open the {self.name} pie menu"}

    def IsActive(self):
        return True

    def Activated(self):
        if runtime is not None:
            runtime.open_pie(self.name)


class Runtime:
    def __init__(self, gui):
        self.gui = gui
        self.pies = {}
        self.binds = {}
        self._keys = {}               # normalised key -> stored key
        self._registered = set()
        self.open_preferences = None  # wired by InitGui once the dialog exists
        self.dispatcher = Dispatcher(
            self._open_for_dispatch, self._resolve,
            open_on_of=lambda n: self.pies[n].open_on if n in self.pies
            else "single")

    # -- model access

    def reload(self):
        self.pies = model.load_pies()
        self.binds = model.load_binds()
        self._keys = {}
        for scope in self.binds.values():
            for key in scope:
                self._keys[QtGui.QKeySequence(key).toString()] = key
        self._register_commands()

    def _register_commands(self):
        for name in self.pies:
            if name in self._registered:
                continue
            try:
                self.gui.addCommand(model.PIE_PREFIX + name, _PieCommand(name))
                self._registered.add(name)
            except Exception:  # noqa: BLE001, S110 -- re-registration is benign
                pass

    # -- resolution

    def counts(self):
        return selection_counts(self.gui)

    def _resolve(self, key):
        """key -> pie name under the active workbench; None key = right-click,
        which opens whatever the lowest bound key resolves to."""
        wb = workbench_scope(self.gui)
        if key is None:
            for k in sorted(self._keys.values()):
                hit = model.resolve_key(k, wb, self.binds)
                if hit:
                    return hit[0]
            return None
        stored = self._keys.get(key, key)
        hit = model.resolve_key(stored, wb, self.binds)
        return hit[0] if hit else None

    # -- opening

    def _open_for_dispatch(self, name):
        return self.open_pie(name)

    def open_pie(self, name):
        if name not in self.pies:
            return None
        widget = PieWidget(self.pies, name, self.counts(), self.fire,
                           quick_menu=self._quick_menu)
        widget.popup_at(QtGui.QCursor.pos())
        self.dispatcher.current = widget
        return widget

    def fire(self, cmd):
        try:
            self.gui.runCommand(cmd, 0)
        except Exception as exc:  # noqa: BLE001 -- a broken command must not kill the pie
            if App is not None:
                App.Console.PrintWarning(f"PieMenu: {cmd} failed: {exc}\n")

    def _quick_menu(self, widget):
        menu = QtWidgets.QMenu(widget)
        act = menu.addAction("Preferences…")
        if self.open_preferences is not None:
            act.triggered.connect(lambda: (widget.close(),
                                           self.open_preferences()))
        else:
            act.setEnabled(False)
        sub = menu.addMenu("Open pie")
        for name in sorted(self.pies):
            sub.addAction(name, lambda n=name: (widget.close(),
                                                self.open_pie(n)))
        menu.exec_(QtGui.QCursor.pos())


def start(gui):
    """Install the v2 runtime: load the model, register commands and the
    app-wide dispatcher.  Called once from InitGui."""
    global runtime
    runtime = Runtime(gui)
    runtime.reload()
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.installEventFilter(runtime.dispatcher)
    return runtime
