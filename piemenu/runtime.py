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

import math
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
        "toggle": p.GetBool("GlobalKeyToggle", True),
        "rclick": p.GetBool("RightClickTrigger", False),
        "rclick_delay": p.GetInt("DelayRightClick", 0) or 350,
    }


def custom_colour(name):
    """The user's colour override for a param, or None."""
    if App is None:
        return None
    try:
        value = _param().GetString(name, "")
    except Exception:  # noqa: BLE001 -- no params outside FreeCAD
        return None
    if value:
        colour = QtGui.QColor(value)
        if colour.isValid():
            return colour
    return None


def accent():
    """The accent colour: the user's override, else the palette highlight."""
    return (custom_colour("AccentColor")
            or QtWidgets.QApplication.palette().highlight().color())


def arrow_colour():
    """The gesture arrow's colour: its own override, else the accent."""
    return custom_colour("ArrowColor") or accent()


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


def pie_icon(pie):
    """A pie's own face: its icon field (a command name), else the first
    real tool inside it, else the logo."""
    if pie is not None:
        candidates = [pie.icon] if pie.icon else []
        candidates += [b.cmd for slot in (pie.items or []) for b in (slot or [])
                       if not is_pie_command(b.cmd)]
        for cmd in candidates:
            icon = command_icon(cmd)
            if icon is not None and not icon.isNull():
                return icon
    return QtGui.QIcon(LOGO)


_ICON_CACHE = {}


def command_icon(cmd):
    """A QIcon for a command, or None.

    A command's QAction only exists once its workbench has been activated,
    so an action-only lookup left every foreign-workbench slot iconless.
    Fall back to the command registry, importing the owning GUI module
    (SketcherGui, PartGui, ...) on first need -- which also registers the
    command so firing it from the pie works before ever visiting its bench.
    """
    if cmd in _ICON_CACHE:
        return _ICON_CACHE[cmd]
    icon = None
    action = command_action(cmd)
    if action is not None and not action.icon().isNull():
        icon = action.icon()
    else:
        icon = _registry_icon(cmd)
    _ICON_CACHE[cmd] = icon
    return icon


def _registry_icon(cmd):
    if App is None or not App.GuiUp:
        return None
    import FreeCADGui as Gui
    getter = getattr(Gui.Command, "get", None)
    if getter is None:
        return None
    command = getter(cmd)
    if command is None:
        try:
            __import__(cmd.split("_", 1)[0] + "Gui")
        except ImportError:
            return None
        command = getter(cmd)
    if command is None:
        return None
    try:
        pixmap = (command.getInfo() or {}).get("pixmap") or ""
        return Gui.getIcon(pixmap) if pixmap else None
    except Exception:  # noqa: BLE001 -- a broken command stays iconless
        return None


# ---- the pie widget --------------------------------------------------------

class PieWidget(QtWidgets.QWidget):
    """One open pie: buttons at model.positions, resolved against counts.

    fire(cmd) runs a command; doors are handled here (open the target pie in
    place) so fire only ever sees runnable commands.
    """

    def __init__(self, pies, name, counts, fire, parent=None):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        fill = custom_colour("FillColor")
        out = custom_colour("OutlineColor")
        fill_css = fill.name() if fill else "palette(button)"
        alt_css = fill.lighter(114).name() if fill \
            else "palette(alternate-base)"
        out_css = out.name() if out else "palette(mid)"
        self.setStyleSheet(
            f"QToolButton{{background:{fill_css};"
            f"border:1px solid {out_css};border-radius:6px;}}"
            f'QToolButton[alt="true"]{{background:{alt_css};}}'
            f"QToolButton:hover{{border:2px solid {accent().name()};}}"
            "QToolButton:disabled{background:palette(window);"
            f"border:1px dashed {out_css};}}")
        self.pies = pies
        self.counts = counts
        self.fire = fire
        self._hover_timer = None
        self._chooser = None
        self._aim = None              # cursor point for the gesture arrow
        self.run_mode = None          # how this pie actually runs, see build()
        self.setMouseTracking(True)
        self.build(name)

    # -- construction

    def build(self, name):
        for child in self.findChildren(QtWidgets.QWidget):
            child.deleteLater()
        self._chooser = None
        self._aim = None
        pie = self.pies[name]
        model.normalise(pie)
        self.pie = pie
        # entered mid-gesture, a sub-pie stays a gesture pie: glide, release
        self.run_mode = "release" if self.run_mode == "release" \
            else pie.run_on
        pos = model.positions(pie)
        pad = 24
        # buttons size themselves (command names grow them), so bounds come
        # from the real widgets, not from pie.button
        self.buttons = [self._slot_button(pie.items[i], i)
                        for i in range(len(pos))]
        if pie.show_names and len(pos) > 1:
            # grown buttons need grown distances or names cover each other
            maxw = max(b.width() for b in self.buttons) + 6
            maxh = max(b.height() for b in self.buttons) + 6
            if pie.family == "circle":
                # neighbours sit a chord apart: scale the radius just
                # enough, judged at the tightest ring
                step = pie.button + pie.spacing + 10
                chord = min(
                    2 * math.sin(math.pi / max(2, c))
                    * max(1, pie.radius + ring * step)
                    for ring, c in enumerate(model.ring_plan(pie, len(pos))))
                scale = max(1.0, maxw / chord, maxh / chord)
            else:
                base = pie.button + pie.spacing
                scale = max(1.0, maxw / base, maxh / base)
            pos = [(x * scale, y * scale) for x, y in pos]
        min_x = min(x - b.width() / 2 for (x, _), b in zip(pos, self.buttons)) - pad
        max_x = max(x + b.width() / 2 for (x, _), b in zip(pos, self.buttons)) + pad
        min_y = min(y - b.height() / 2 for (_, y), b in zip(pos, self.buttons)) - pad
        max_y = max(y + b.height() / 2 for (_, y), b in zip(pos, self.buttons)) + pad
        # the cursor anchor must sit at (0,0) of the layout
        self._origin = (-min_x, -min_y)
        self.resize(int(max_x - min_x), int(max_y - min_y))
        for (x, y), btn in zip(pos, self.buttons):
            btn.move(int(x - min_x - btn.width() / 2),
                     int(y - min_y - btn.height() / 2))

    def _slot_button(self, slot, index):
        pie = self.pie
        btn = QtWidgets.QToolButton(self)
        btn.setFixedSize(pie.button, pie.button)
        btn.setIconSize(QtCore.QSize(int(pie.button * 0.6), int(pie.button * 0.6)))
        live = model.live_bindings(slot, self.counts)
        face = model.slot_face(slot, self.counts, pie.last_used.get(index))
        binding = face if face else (slot[0] if slot else None)
        if binding is None:
            btn.setEnabled(False)
            btn.setVisible(False)
            return btn
        self._decorate(btn, binding, bool(live), len(live))
        if live:
            if len(live) > 1:
                btn.installEventFilter(_ChooserFilter(self, btn, live))
            btn.clicked.connect(
                lambda _=False, cmd=face.cmd: self.activate(cmd))
            if self.run_mode == "hover":
                btn.installEventFilter(_HoverFire(self, btn, face.cmd,
                                                  pie.delay))
            elif pie.door_hover and is_pie_command(face.cmd):
                # dwelling on a door descends into it mid-gesture
                btn.installEventFilter(_HoverFire(self, btn, face.cmd,
                                                  pie.delay))
        if index % 2 and not is_pie_command(binding.cmd):
            btn.setProperty("alt", True)     # alternate fill, odd slots
        # explicit: children born on an ALREADY-VISIBLE parent stay hidden
        # otherwise -- a door descend rebuilds while shown, and every button
        # of the sub-pie would be invisible (the pie "not spawning")
        btn.setVisible(True)
        return btn

    def _decorate(self, btn, binding, live, n_live):
        cmd = binding.cmd
        tip = cmd
        if is_pie_command(cmd):
            target = pie_target(cmd)
            btn.setIcon(pie_icon(self.pies.get(target)))
            tip = f"Open {target}"
            dead = not model.pie_live(target, self.pies, self.counts)
            colour = "#808080" if (dead or not live) else accent().name()
            btn.setStyleSheet(
                f"QToolButton{{border:2px solid {colour};"
                f"border-radius:{self.pie.button // 2}px;}}")
            live = live and not dead
        else:
            icon = command_icon(cmd)
            if icon is not None:
                btn.setIcon(icon)
            action = command_action(cmd)
            if action is not None:
                tip = action.toolTip() or cmd
        if self.pie.show_names:
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            text = pie_target(cmd) if is_pie_command(cmd) \
                else cmd.split("_", 1)[-1]
            btn.setText(text)
            # a 34px square clips text-under-icon into nothing: size from the
            # style's own hint (font metrics undercount once a theme
            # stylesheet swaps fonts in), plus margin
            hint = btn.sizeHint()
            btn.setFixedSize(
                max(self.pie.button, hint.width() + 10),
                max(self.pie.button + btn.fontMetrics().height() + 6,
                    hint.height() + 4))
        if n_live > 1:
            tip += f"  ({n_live} apply — hover to choose)"
        btn.setToolTip(tip)
        btn.setEnabled(bool(live))

    # -- behaviour

    def choose(self, index, cmd):
        """A chooser pick: remember it as the slot's face, then run it."""
        self.pie.last_used[index] = cmd
        model.set_last_used(self.pie.name, index, cmd)
        self.activate(cmd)

    def activate(self, cmd):
        """Run a command, or descend into a pie at the same spot."""
        if is_pie_command(cmd):
            target = pie_target(cmd)
            if target in self.pies:
                # the sub-pie spawns where the hand already is
                self.build(target)
                self.popup_at(QtGui.QCursor.pos())
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

    def commit_gesture(self, pos=None):
        """Release in a hold pie: run whatever the cursor is aimed at.

        A chooser alternative near the cursor wins over its parent slot;
        an overloaded slot itself just fires its face -- the chooser is
        only for reaching the alternatives."""
        pos = QtGui.QCursor.pos() if pos is None else pos
        if self._chooser is not None:
            local = self._chooser.mapFromGlobal(pos)
            if self._chooser.rect().adjusted(-10, -10, 10, 10).contains(local):
                alts = self._chooser.findChildren(QtWidgets.QToolButton)
                if alts:
                    min(alts, key=lambda a: abs(
                        a.geometry().center().x() - local.x())).click()
                    return
        origin = self.mapToGlobal(QtCore.QPoint(int(self._origin[0]),
                                                int(self._origin[1])))
        dx, dy = pos.x() - origin.x(), pos.y() - origin.y()
        if (dx * dx + dy * dy) ** 0.5 < max(24, self.pie.radius * 0.45):
            self.close()             # released from the dead-zone: no aim
            return
        btn = self.nearest_slot(pos)
        if btn is None:
            self.close()
            return
        btn.click()

    # -- the gesture arrow (release mode): centre -> cursor

    def mouseMoveEvent(self, event):
        if self.run_mode == "release":
            self._aim = event.position().toPoint() \
                if hasattr(event, "position") else event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.run_mode != "release" or self._aim is None:
            return
        p1 = QtCore.QPointF(self._origin[0], self._origin[1])
        p2 = QtCore.QPointF(self._aim)
        line = QtCore.QLineF(p1, p2)
        length = line.length()
        if length < 12:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        colour = arrow_colour()
        # a tapered swoosh: hairline at the origin widening toward the tip,
        # fading in as it goes, finished with a slender head
        ux, uy = (p2.x() - p1.x()) / length, (p2.y() - p1.y()) / length
        nx, ny = -uy, ux
        head = min(18.0, length * 0.35)
        neck = QtCore.QPointF(p2.x() - ux * head, p2.y() - uy * head)
        w0, w1, wh = 0.8, 4.0, 8.5
        faint = QtGui.QColor(colour)
        faint.setAlpha(46)
        solid = QtGui.QColor(colour)
        solid.setAlpha(235)
        grad = QtGui.QLinearGradient(p1, p2)
        grad.setColorAt(0.0, faint)
        grad.setColorAt(1.0, solid)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(grad)
        painter.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(p1.x() + nx * w0, p1.y() + ny * w0),
            QtCore.QPointF(neck.x() + nx * w1, neck.y() + ny * w1),
            QtCore.QPointF(neck.x() - nx * w1, neck.y() - ny * w1),
            QtCore.QPointF(p1.x() - nx * w0, p1.y() - ny * w0)]))
        painter.setBrush(solid)
        painter.drawPolygon(QtGui.QPolygonF([
            p2,
            QtCore.QPointF(neck.x() + nx * wh, neck.y() + ny * wh),
            QtCore.QPointF(neck.x() - nx * wh, neck.y() - ny * wh)]))
        painter.setBrush(faint)
        painter.drawEllipse(p1, 3, 3)
        painter.end()


class _DwellRing(QtWidgets.QWidget):
    """A circular fill on a dwell-armed button: time until it activates."""

    def __init__(self, btn):
        super().__init__(btn)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.progress = 0.0
        self.resize(btn.size())
        self.hide()

    def paintEvent(self, _event):
        if self.progress <= 0:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(accent(), 3,
                                  QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        painter.drawArc(self.rect().adjusted(2, 2, -2, -2),
                        90 * 16, int(-360 * 16 * self.progress))
        painter.end()


class _HoverFire(QtCore.QObject):
    """Dwelling on an armed slot for the delay fires it (hover mode slots,
    hover doors).  A ring fills clockwise to show time-to-activation."""

    TICK = 25

    def __init__(self, pie_widget, btn, cmd, delay):
        super().__init__(btn)
        self.w, self.cmd = pie_widget, cmd
        self.delay = max(50, delay)
        self.elapsed = 0
        self.ring = _DwellRing(btn)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.delay)
        self.timer.timeout.connect(self._fire)
        self.tick = QtCore.QTimer(self)
        self.tick.setInterval(self.TICK)
        self.tick.timeout.connect(self._tick)

    def _fire(self):
        self.tick.stop()
        self.ring.hide()
        self.w.activate(self.cmd)

    def _tick(self):
        self.elapsed += self.TICK
        self.ring.progress = min(1.0, self.elapsed / self.delay)
        self.ring.update()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Enter:
            self.elapsed = 0
            self.ring.progress = 0.0
            self.ring.resize(obj.size())
            self.ring.show()
            self.ring.raise_()
            self.timer.start()
            self.tick.start()
        elif event.type() == QtCore.QEvent.Leave:
            self.timer.stop()
            self.tick.stop()
            self.ring.hide()
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
    index = pie_widget.buttons.index(btn)
    box = QtWidgets.QWidget(pie_widget)
    lay = QtWidgets.QHBoxLayout(box)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    size = max(16, pie_widget.pie.alt_size)
    for b in bindings:
        alt = QtWidgets.QToolButton(box)
        alt.setIconSize(QtCore.QSize(int(size * 0.75), int(size * 0.75)))
        pie_widget._decorate(alt, b, True, 1)
        alt.setFixedSize(size, size)
        alt.clicked.connect(
            lambda _=False, cmd=b.cmd: pie_widget.choose(index, cmd))
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
    """App-wide key handling: the gesture belongs to the binding.

    Four gestures per key — press, double, hold, double-hold. Every press
    decides between a QUICK outcome (tap / double-tap) and a HELD one
    (hold / double-hold): when both exist the pie defers ~170ms, an early
    release resolves to the quick pie, holding (or moving the mouse)
    resolves to the held one anchored at the press point. What RELEASE
    means is the pie's own run mode: a release pie follows the aim and
    never outlives the key (centre dead-zone just closes); a click/hover
    pie stays for the mouse and toggles. Also the long right-click
    trigger.
    """

    DOUBLE_MS = 350
    DEFER_MS = 170

    def __init__(self, opener, gestures, fallback=None, mode_of=None,
                 parent=None):
        super().__init__(parent)
        self.opener = opener          # opener(pie_name) -> PieWidget|None
        self.gestures = gestures      # gestures(key) -> {gesture: pie_name}
        self.fallback = fallback or (lambda: None)   # the right-click pie
        self.mode_of = mode_of or (lambda name: "click")   # pie's run_on
        self.current = None           # the open PieWidget
        self.last_tap = {}            # key -> ms timestamp
        self.held = None              # the key currently down
        self._rtimer = None
        self._swallow_context = False
        self._defer = QtCore.QTimer(self)
        self._defer.setSingleShot(True)
        self._defer.setInterval(self.DEFER_MS)
        self._defer.timeout.connect(self._open_deferred)
        self._deferred = None         # (key, pie name) waiting on the timer
        self._press_pos = QtCore.QPoint()

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
        return (now - last) < self.DOUBLE_MS

    def _open_deferred(self):
        if self._deferred is None:
            return
        key, _quick, held = self._deferred
        self._deferred = None
        if self.held == key and held is not None:
            # the hand is still down: the held outcome, anchored at the
            # press point so movement so far counts as aim
            self.open_pie(held, at=self._press_pos)
            self.held = key           # open_pie's close() cleared it

    def open_pie(self, name, at=None):
        self.close()
        self.current = self.opener(name, at)
        return self.current

    def _reuse(self, name):
        """True when the open pie already is `name` — keep it, no flicker."""
        return (self.current is not None and self.current.isVisible()
                and self.current.pie.name == name)

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
        if etype == QtCore.QEvent.MouseMove and self._deferred is not None:
            # moving right after the press means a gesture, not a tap:
            # show the pie now instead of waiting out the double window
            pos = QtGui.QCursor.pos()
            dx = pos.x() - self._press_pos.x()
            dy = pos.y() - self._press_pos.y()
            if dx * dx + dy * dy > 100:
                self._defer.stop()
                self._open_deferred()
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

    def _typing_focus(self):
        """Never hijack keys aimed at a text field or a modal dialog."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        if app.activeModalWidget() is not None:
            return True
        w = app.focusWidget()
        return isinstance(w, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                              QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit,
                              QtWidgets.QKeySequenceEdit))

    def _key_press(self, event):
        if self._typing_focus():
            return False
        key = self._key_of(event)
        gmap = self.gestures(key)
        if not gmap:
            return False
        now = _now_ms()
        double_ready = self._double(key, now)
        self._defer.stop()
        self._deferred = None
        # every press decides between a QUICK outcome (tap / double-tap) and
        # a HELD outcome (hold / double-hold)
        if double_ready:
            quick, held = gmap.get("double"), gmap.get("double-hold")
            if quick is None and held is None:
                # no double side on this key: a fast second press is just
                # another press (fast toggling must keep working)
                quick, held = gmap.get("press"), gmap.get("hold")
        else:
            quick, held = gmap.get("press"), gmap.get("hold")
        if quick is None and held is None:
            return True      # nothing this round; the window is armed
        ambiguous = held is not None and held != quick
        if not ambiguous and not double_ready and quick is not None \
                and self.mode_of(quick) == "release" \
                and ("double" in gmap or "double-hold" in gmap):
            # a gesture pie ahead of a possible double: wait it out so a
            # quick tap is a no-op and a double-tap never flickers
            held = quick
            ambiguous = True
        if not ambiguous:
            name = quick if quick is not None else held
            if self._reuse(name):
                # the same pie is already up: a persistent pie toggles shut
                # (only when this key has no other gesture to protect)
                if (self.mode_of(name) != "release"
                        and behaviour()["toggle"] and set(gmap) <= {"press"}):
                    self.close()
                    return True
            else:
                self.open_pie(name)
            self.held = key
            return True
        # ambiguous: hold (or movement) opens the held pie; an early
        # release resolves to the quick one
        self._deferred = (key, quick, held)
        self._press_pos = QtGui.QCursor.pos()
        self._defer.start()
        self.held = key
        return True

    def _key_release(self, event):
        if self.held is None:
            return False
        if self._key_of(event) != self.held:
            return False
        self.held = None
        if self._deferred is not None:
            # released before the held outcome: this was a tap
            _key, quick, _held = self._deferred
            self._defer.stop()
            self._deferred = None
            if quick is not None and self.mode_of(quick) != "release" \
                    and not self._reuse(quick):
                # a persistent quick pie opens where the press happened;
                # a release pie on a completed tap means nothing at all
                self.open_pie(quick, at=self._press_pos)
            return True
        widget = self.current
        if widget is None:
            return False
        if getattr(widget, "run_mode", widget.pie.run_on) != "release":
            return True      # a persistent pie stays for the mouse
        widget.commit_gesture()      # fire the aim, or vanish from the centre
        if widget.isVisible():
            return True      # a door or a chooser keeps it up
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
        name = self.fallback()
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
            self._open_for_dispatch, self._gestures,
            fallback=lambda: self._resolve(None),
            mode_of=lambda n: self.pies[n].run_on if n in self.pies
            else "click")

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
            except Exception as exc:  # noqa: BLE001 -- re-registration is benign
                if App is not None:
                    App.Console.PrintWarning(
                        f"PieMenu: addCommand {name} failed: {exc}\n")

    # -- resolution

    def counts(self):
        return selection_counts(self.gui)

    def _gestures(self, key):
        """key -> {gesture: pie name} under the active workbench."""
        wb = workbench_scope(self.gui)
        stored = self._keys.get(key, key)
        return {g: hit[0] for g, hit
                in model.gestures_for(stored, wb, self.binds).items()}

    def _resolve(self, key):
        """key -> press pie name; None key = right-click, which opens what
        the lowest bound key answers with (press first, then any gesture)."""
        wb = workbench_scope(self.gui)
        if key is None:
            for k in sorted(self._keys.values()):
                hits = model.gestures_for(k, wb, self.binds)
                if hits:
                    hit = hits.get("press")
                    return (hit or next(iter(hits.values())))[0]
            return None
        stored = self._keys.get(key, key)
        hit = model.resolve_key(stored, wb, self.binds)
        return hit[0] if hit else None

    # -- opening

    def _open_for_dispatch(self, name, at=None):
        return self.open_pie(name, at)

    def open_pie(self, name, at=None):
        if name not in self.pies:
            return None
        widget = PieWidget(self.pies, name, self.counts(), self.fire)
        widget.popup_at(at if at is not None and not at.isNull()
                        else QtGui.QCursor.pos())
        self.dispatcher.current = widget
        return widget

    def fire(self, cmd):
        try:
            self.gui.runCommand(cmd, 0)
        except Exception as exc:  # noqa: BLE001 -- a broken command must not kill the pie
            if App is not None:
                App.Console.PrintWarning(f"PieMenu: {cmd} failed: {exc}\n")


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
