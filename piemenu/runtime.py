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

import itertools
import math
import os
from collections import deque

from PySide import QtCore, QtGui, QtWidgets

try:
    import FreeCAD as App
except ImportError:
    App = None

from . import model, resources
from .model import is_pie_command, pie_target

MAIN = "User parameter:BaseApp/PieMenu"
LOGO = os.path.join(resources.respath, "PieMenu_Logo.svg")

# the spare thumb buttons; FreeCAD's navigation never uses them, and they
# bind exactly like keys (all four gestures)
MOUSE_KEYS = {QtCore.Qt.XButton1: "Mouse4", QtCore.Qt.XButton2: "Mouse5"}

runtime = None      # the singleton, created by start()


def _param():
    return App.ParamGet(MAIN)


def behaviour():
    p = _param()
    return {
        "toggle": p.GetBool("GlobalKeyToggle", True),
        "rclick": p.GetBool("RightClickTrigger", False),
        "rclick_delay": p.GetInt("DelayRightClick", 0) or 350,
        "autoopen": p.GetBool("AutoOpenSelection", False),
        "opaque": p.GetBool("OpaquePies", False),
    }


# the two built-in looks; explicit color overrides still beat them
THEMES = {
    "light": {"fill": "#f0f0f0", "outline": "#b9b9b9",
              "text": "#2f2f2f", "window": "#fafafa"},
    "dark": {"fill": "#3c3c3c", "outline": "#5a5a5a",
             "text": "#e4e4e4", "window": "#2d2d2d"},
}


def active_theme():
    """"light", "dark", or "" for following the FreeCAD palette."""
    if App is None:
        return ""
    try:
        name = _param().GetString("Theme", "")
    except Exception:  # noqa: BLE001 -- no params outside FreeCAD
        return ""
    return name if name in THEMES else ""


def custom_color(name):
    """The user's color override for a param, or None."""
    if App is None:
        return None
    try:
        value = _param().GetString(name, "")
    except Exception:  # noqa: BLE001 -- no params outside FreeCAD
        return None
    if value:
        color = QtGui.QColor(value)
        if color.isValid():
            return color
    return None


def accent():
    """The accent color: the user's override, else the palette highlight."""
    return (custom_color("AccentColor")
            or QtWidgets.QApplication.palette().highlight().color())


def arrow_color():
    """The gesture arrow's color: its own override, else the accent."""
    return custom_color("ArrowColor") or accent()


def workbench_scope(gui):
    """The active scope: "SketchEdit" while a sketch is being edited,
    else the active workbench's name ("PartDesign")."""
    try:
        active_doc = getattr(gui, "ActiveDocument", None)
        edit = active_doc.getInEdit() if active_doc is not None else None
        obj = getattr(edit, "Object", None)
        if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
            return model.SKETCH_EDIT_SCOPE
    except Exception:  # noqa: BLE001, S110 -- no edit session
        pass
    try:
        return gui.activeWorkbench().name().split("Workbench")[0]
    except Exception:  # noqa: BLE001 -- half-built Gui in console mode
        return ""


class HaloLabel(QtWidgets.QLabel):
    """Text drawn with a thin rim of the opposite luminance, so it reads
    over any scene without sampling what's behind it (Wayland forbids
    that anyway). A crisp stroked outline, not a blur: blurs wash out
    against busy geometry."""

    PAD = 3

    def __init__(self, text, parent, color="#999", px=10):
        super().__init__(text, parent)
        self._color = QtGui.QColor(color)
        font = self.font()
        font.setPixelSize(px)
        self.setFont(font)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def sizeHint(self):
        base = super().sizeHint()
        return QtCore.QSize(base.width() + 2 * self.PAD,
                            base.height() + 2 * self.PAD)

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.addText(self.PAD, self.PAD + self.fontMetrics().ascent(),
                     self.font(), self.text())
        rim = QtGui.QColor(0, 0, 0, 200) \
            if self._color.lightness() >= 128 \
            else QtGui.QColor(255, 255, 255, 200)
        painter.strokePath(path, QtGui.QPen(
            rim, 3.0, QtCore.Qt.SolidLine,
            QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.fillPath(path, self._color)


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


def shape_radius(pie, shape=None):
    """The corner radius a shape asks for, in pixels."""
    return {"square": 0, "rounded": 6,
            "squircle": max(6, int(pie.button * 0.32)),
            "circle": pie.button // 2}.get(shape or pie.shape, 6)


def workbench_icon(name):
    """A workbench's own icon, by full name or scope prefix, or None.

    Workbench entries are not commands: no QAction, nothing in the
    registry. Their icon lives on the workbench object (XPM text for
    python benches, a resource path for C++ ones).
    """
    if App is None or not App.GuiUp:
        return None
    if name == model.SKETCH_EDIT_SCOPE:
        name = "Sketcher"             # wears the Sketcher icon
    try:
        import FreeCADGui as Gui
        benches = Gui.listWorkbenches()
        wb = benches.get(name) or benches.get(name + "Workbench") or next(
            (w for k, w in benches.items() if k.startswith(name)), None)
        xpm = getattr(wb, "Icon", "") if wb is not None else ""
        if xpm.startswith((":", "/")) or xpm.endswith((".svg", ".png")):
            icon = QtGui.QIcon(xpm)
            if not icon.isNull():
                return icon
        elif xpm:
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(bytes(xpm, "utf-8"), "XPM"):
                return QtGui.QIcon(pixmap)
    except Exception:  # noqa: BLE001 -- console mode / exotic benches
        return None
    return None


# positive-sticky availability caches: a yes is stable until reload, a
# no is re-checked every time (a workbench can appear mid-session), so
# building a pie stops paying a registry scan per slot per open
_AVAILABLE = {"prefix": set(), "cmd": set()}


def prefix_available(prefix):
    if prefix in _AVAILABLE["prefix"]:
        return True
    ok = _prefix_available_uncached(prefix)
    if ok:
        _AVAILABLE["prefix"].add(prefix)
    return ok


def _prefix_available_uncached(prefix):
    """Can commands with this prefix exist here? Cheap: no module import."""
    if prefix == "Std" or not prefix:
        return True
    if App is None or not App.GuiUp:
        return True                   # headless: assume yes, never disable
    try:
        import FreeCADGui as Gui
        if any(k.startswith(prefix) for k in Gui.listWorkbenches()):
            return True
    except Exception:  # noqa: BLE001 -- half-built Gui
        return True
    import importlib.util
    try:
        return importlib.util.find_spec(prefix + "Gui") is not None
    except (ImportError, ValueError):
        return False


def panel_open():
    """Is a task panel (Pad, Fillet, sketch tools...) currently up?"""
    if App is None or not App.GuiUp:
        return False
    try:
        import FreeCADGui as Gui
        return Gui.Control.activeDialog() is not None
    except Exception:  # noqa: BLE001 -- half-built Gui
        return False


def command_available(cmd):
    if cmd in _AVAILABLE["cmd"]:
        return True
    ok = _command_available_uncached(cmd)
    if ok:
        _AVAILABLE["cmd"].add(cmd)
    return ok


def _command_available_uncached(cmd):
    """False when a command's workbench/addon is not installed here."""
    if is_pie_command(cmd):
        return True                   # doors are validated against pies
    if cmd.startswith(model.PANEL_PREFIX):
        return True                   # built in, liveness is contextual
    if cmd.startswith(model.MACRO_PREFIX):
        if App is None:
            return True
        try:
            return os.path.exists(os.path.join(
                App.getUserMacroDir(True), cmd[len(model.MACRO_PREFIX):]))
        except Exception:  # noqa: BLE001 -- no macro dir
            return True
    if command_action(cmd) is not None:
        return True
    if cmd.endswith("Workbench") and "_" not in cmd:
        return prefix_available(cmd[:-len("Workbench")])
    return prefix_available(cmd.split("_", 1)[0] if "_" in cmd else "")


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
    if cmd.startswith(model.PANEL_PREFIX):
        style = QtWidgets.QApplication.style()
        icon = style.standardIcon(
            {"OK": QtWidgets.QStyle.SP_DialogOkButton,
             "Apply": QtWidgets.QStyle.SP_DialogApplyButton,
             "Cancel": QtWidgets.QStyle.SP_DialogCancelButton}.get(
                cmd[len(model.PANEL_PREFIX):],
                QtWidgets.QStyle.SP_DialogOkButton))
        _ICON_CACHE[cmd] = icon
        return icon
    if cmd.startswith(model.MACRO_PREFIX):
        icon = command_icon("Std_DlgMacroExecute")
        _ICON_CACHE[cmd] = icon
        return icon
    if cmd.endswith("Workbench"):
        icon = workbench_icon(cmd)
        if icon is not None:
            _ICON_CACHE[cmd] = icon
            return icon
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

    def __init__(self, pies, name, counts, fire, runtime=None, parent=None,
                 pinned=False, mode=None):
        # a pinned palette is born with its final window role: inside the
        # main window as a plain child when there is one, else a Tool
        # window. Re-flagging a live popup crashes under Wayland (a
        # surface's role can never change).
        if pinned:
            flags = QtCore.Qt.Widget if parent is not None else (
                QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                | QtCore.Qt.WindowStaysOnTopHint)
        else:
            flags = QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint
        super().__init__(parent, flags)
        # without a compositor (bare X11, VNC) translucency renders as a
        # black rectangle — the OpaquePies switch paints a solid panel
        try:
            self._opaque = behaviour()["opaque"]
        except Exception:  # noqa: BLE001 -- no params outside FreeCAD
            self._opaque = False
        if not self._opaque:
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.pies = pies
        self.counts = counts
        self.fire = fire
        self._rt = runtime
        self.pinned = pinned
        self._drag_at = None
        self._snapped_edge = None     # pinned palette resting on an edge
        self._collapsed = False
        self._expanded_geo = None
        self._sectors = []            # (ring, radius, angle, btn) circles
        self._aimed = None            # slot currently ringed by the aim
        self._aim_stick = None        # incumbent slot at sector boundaries
        self._hover_timer = None
        self._chooser = None
        self._aim = None              # cursor point for the gesture arrow
        # a pie opened by a HOLD is a marking menu whatever its own
        # run_on says; build() keeps "release" once set (doors inherit)
        self.run_mode = mode
        self._stack = []              # door trail, for the back button
        self.setMouseTracking(True)
        self.build(name)
        if pinned:
            self.setFocusPolicy(QtCore.Qt.ClickFocus)   # Esc after a click
            self._pin_close_button()

    # -- construction

    def build(self, name):
        for child in self.findChildren(QtWidgets.QWidget):
            child.deleteLater()
        self._chooser = None
        self._aim = None
        self._aimed = None
        self._aim_stick = None
        pie = self.pies[name]
        model.normalise(pie)
        own = QtGui.QColor(pie.accent) if pie.accent else QtGui.QColor()
        self._accent = own if own.isValid() else accent()
        theme = active_theme()
        spec = THEMES.get(theme, {})
        fill = custom_color("FillColor") or (
            QtGui.QColor(spec["fill"]) if spec else None)
        out = custom_color("OutlineColor") or (
            QtGui.QColor(spec["outline"]) if spec else None)
        fill_css = fill.name() if fill else "palette(button)"
        if fill:
            alt = fill.darker(106) if theme == "light" \
                else fill.lighter(114)
            alt_css = alt.name()
        else:
            alt_css = "palette(alternate-base)"
        out_css = out.name() if out else "palette(mid)"
        text_css = f"color:{spec['text']};" if spec else ""
        win_css = spec["window"] if spec else "palette(window)"
        self._panel_color = QtGui.QColor(spec["window"]) if spec else None
        radius = shape_radius(pie)
        border = f"border:1px solid {out_css};"
        alt_rule = f'QToolButton[alt="true"]{{background:{alt_css};}}'
        if pie.style == "gradient":
            base = fill or QtWidgets.QApplication.palette().button().color()
            fill_css = ("qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                        f"stop:0 {base.lighter(112).name()},"
                        f"stop:1 {base.darker(108).name()})")
            alt_rule = ""
        elif pie.style == "outline":
            fill_css = "transparent"
            border = f"border:2px solid {out_css};"
            alt_rule = ""
        elif pie.style == "soft":
            border = "border:none;"        # fill only, no edges at all
        elif pie.style == "glass":
            base = fill or QtWidgets.QApplication.palette().button().color()
            edge = out or QtWidgets.QApplication.palette().mid().color()
            fill_css = (f"rgba({base.red()},{base.green()},"
                        f"{base.blue()},170)")
            border = (f"border:1px solid rgba({edge.red()},"
                      f"{edge.green()},{edge.blue()},120);")
            alt_rule = ""
        elif pie.style == "bold":
            border = f"border:2px solid {out_css};"
        elif pie.style == "minimal":
            fill_css = "transparent"       # bare icons, hover ring only
            border = "border:none;"
            alt_rule = ""
        # background-image:none beats theme stylesheets that paint
        # QToolButton with images, which otherwise mask our fill entirely
        self._base_css = (f"background:{fill_css};background-image:none;"
                          f"{text_css}{border}")
        acc = self._accent
        self.setStyleSheet(
            f"QToolButton{{{self._base_css}border-radius:{radius}px;}}"
            f"{alt_rule}"
            # the tool fired last time gets a faint accent ring, a small
            # anchor for muscle memory
            f'QToolButton[last="true"]{{border:1px solid '
            f"rgba({acc.red()},{acc.green()},{acc.blue()},150);}}"
            # the slot the gesture is aimed at right now
            f'QToolButton[aimed="true"]{{border:2px solid '
            f"{self._accent.name()};}}"
            f"QToolButton:hover{{border:2px solid {self._accent.name()};}}"
            f"QToolButton:disabled{{background:{win_css};"
            f"border:1px dashed {out_css};}}")
        self.pie = pie
        try:
            self._last_fired = model.last_fired(pie.name)
        except Exception:  # noqa: BLE001 -- no params outside FreeCAD
            self._last_fired = ""
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
        # circle pies resolve the aim by direction: remember each slot's
        # ring and angle (screen coords, y down). Grids stay distance-based.
        self._sectors = []
        if pie.family == "circle":
            plan = model.ring_plan(pie, len(pos))
            ring, k = 0, 0
            for (x, y), btn in zip(pos, self.buttons):
                self._sectors.append(
                    (ring, math.hypot(x, y), math.atan2(y, x), btn))
                k += 1
                if k >= plan[ring]:
                    ring, k = ring + 1, 0
        # the pie says its name at the centre, so you always know which
        # one answered the key
        name_label = HaloLabel(pie.name, self, "#999", 10)
        name_label.adjustSize()
        name_label.move(int(self._origin[0] - name_label.width() / 2),
                        int(self._origin[1] - name_label.height() / 2))
        name_label.setVisible(True)
        self._name_label = name_label
        digit = 0
        for btn in self.buttons:      # 1..9 and letter accels, as tags
            if btn.isHidden() or not btn.isEnabled():
                continue
            accel = btn.property("accel") or ""
            if accel:                 # its own letter beats the number
                tag = HaloLabel(accel, btn, self._accent.name(), 9)
            elif digit < 9:
                digit += 1
                tag = HaloLabel(str(digit), btn, "#888", 9)
            else:
                continue
            tag.adjustSize()
            tag.move(btn.width() - tag.width() - 1, -1)
            tag.setVisible(True)

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
        if face is not None:
            btn.setProperty("cmd", face.cmd)   # for blind marks + Doctor
        if live:
            if len(live) > 1:
                btn.installEventFilter(_ChooserFilter(self, btn, live))
            btn.clicked.connect(
                lambda _=False, cmd=face.cmd: self.activate(cmd))
            if self.run_mode == "hover":
                btn.installEventFilter(_HoverFire(self, btn, face.cmd,
                                                  pie.delay))
            elif pie.door_hover and is_pie_command(face.cmd):
                # dwelling on a door descends into it mid-gesture;
                # instant doors skip the dwell, and a gesture in flight
                # gets a fast fixed dwell so the stroke keeps moving
                if pie.door_instant:
                    dwell = 0
                elif self.run_mode == "release":
                    dwell = 100
                else:
                    dwell = pie.delay
                btn.installEventFilter(_HoverFire(
                    self, btn, face.cmd, dwell))
        if index % 2 and not is_pie_command(binding.cmd):
            btn.setProperty("alt", True)     # alternate fill, odd slots
        if self._last_fired and binding.cmd == self._last_fired:
            btn.setProperty("last", True)    # fired last time: faint ring
        if binding.accel:
            btn.setProperty("accel", binding.accel[:1].upper())
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda _pos, i=index, b=btn: self._slot_menu(i, b))
        # explicit: children born on an ALREADY-VISIBLE parent stay hidden
        # otherwise -- a door descend rebuilds while shown, and every button
        # of the sub-pie would be invisible (the pie "not spawning")
        btn.setVisible(True)
        return btn

    def _slot_menu(self, index, _btn):
        """Right-click a live slot: edit it without the big dialog. In the
        Smart pie, pin or unpin the tool instead (its slots are computed)."""
        if self._rt is None:
            return
        slot = self.pie.items[index]
        face = model.slot_face(slot, self.counts,
                               self.pie.last_used.get(index))
        if face is None:
            return
        if self.pie.name == model.SMART_NAME:
            cmd = face.cmd
            kept = cmd in model.smart_favorites()
            shunned = cmd in model.smart_ignored()
            menu = QtWidgets.QMenu(self)
            menu.addAction(
                "Unpin from Smart" if kept else "Keep in Smart",
                lambda: model.set_smart_favorite(cmd, not kept))
            menu.addAction(
                "Stop ignoring" if shunned else "Ignore in Smart",
                lambda: model.set_smart_ignored(cmd, not shunned))
            menu.exec_(QtGui.QCursor.pos())
            return
        j = slot.index(face)
        menu = QtWidgets.QMenu(self)
        menu.addAction("Replace tool…",
                       lambda: self._live_edit(index, j, "replace"))
        menu.addAction("Edit rule…",
                       lambda: self._live_edit(index, j, "rule"))
        menu.addAction("Rename label…",
                       lambda: self._live_edit(index, j, "label"))
        menu.addAction("Shortcut letter…",
                       lambda: self._live_edit(index, j, "accel"))
        menu.addAction("Remove",
                       lambda: self._live_edit(index, j, "remove"))
        menu.exec_(QtGui.QCursor.pos())

    def _live_edit(self, i, j, what):
        from . import dialog as dialog_mod  # lazy: dialog imports runtime
        rt = self._rt
        name = self.pie.name
        self.close()
        pie = rt.pies.get(name)
        if pie is None or not pie.items[i]:
            return
        slot = pie.items[i]
        j = min(j, len(slot) - 1)
        if what == "replace":
            picker = dialog_mod.PickerDialog(rt.pies, pie, slot,
                                             replace_binding=slot[j])
            if picker.exec_() == QtWidgets.QDialog.Accepted:
                got = picker.result_binding()
                if got:
                    slot[j] = got
        elif what == "rule":
            dialog_mod.edit_rule(None, slot[j], lambda: None)
        elif what == "label":
            text, ok = QtWidgets.QInputDialog.getText(
                None, "Slot label", "Shown instead of the command name:",
                text=slot[j].label)
            if ok:
                slot[j].label = text.strip()
        elif what == "accel":
            text, ok = QtWidgets.QInputDialog.getText(
                None, "Shortcut letter",
                "One letter fires this slot while the pie is open\n"
                "(blank removes it):", text=slot[j].accel)
            if ok:
                slot[j].accel = text.strip()[:1].upper()
        elif what == "remove":
            slot.pop(j)
            if not slot:
                pie.items[i] = None
        model.save_pie(pie)
        rt.reload()

    def _decorate(self, btn, binding, live, n_live):
        cmd = binding.cmd
        tip = cmd
        if is_pie_command(cmd):
            target = pie_target(cmd)
            btn.setIcon(pie_icon(self.pies.get(target)))
            tip = f"Open {target}"
            dead = not model.pie_live(target, self.pies, self.counts)
            color = "#808080" if (dead or not live) else self._accent.name()
            btn.setStyleSheet(
                f"QToolButton{{border:2px solid {color};"
                f"border-radius:{shape_radius(self.pie)}px;}}")
            live = live and not dead
        else:
            icon = command_icon(cmd)
            if icon is not None:
                btn.setIcon(icon)
            action = command_action(cmd)
            if action is not None:
                tip = action.toolTip() or cmd
        if not is_pie_command(cmd) and not command_available(cmd):
            # the tool's workbench is not installed: visibly dead, and says why
            live = False
            tip += "  — not available; is its workbench installed?"
        if cmd.startswith(model.PANEL_PREFIX) and not panel_open():
            live = False
            tip = f"{cmd[len(model.PANEL_PREFIX):]} — no task panel open"
        if binding.label:
            text = binding.label
        elif cmd.startswith(model.PANEL_PREFIX):
            text = cmd[len(model.PANEL_PREFIX):]
        elif is_pie_command(cmd):
            text = pie_target(cmd)
        elif cmd.endswith("Workbench") and "_" not in cmd:
            text = cmd[:-len("Workbench")]
        else:
            text = cmd.split("_", 1)[-1]
        btn.setProperty("aimname", text)     # the centre readout's word
        if self.pie.show_names:
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
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

    def activate(self, cmd, sticky=None):
        """Run a command, or descend into a pie at the same spot.

        Shift held = sticky: fire without closing, chain several tools.
        Pinned palettes never close on fire."""
        if is_pie_command(cmd):
            target = pie_target(cmd)
            if target in self.pies:
                # the sub-pie spawns where the hand already is (a pinned
                # palette stays where it is)
                anchor = self.mapToGlobal(QtCore.QPoint(
                    int(self._origin[0]), int(self._origin[1]))) \
                    if self.pinned else QtGui.QCursor.pos()
                self._stack.append(self.pie.name)
                self.build(target)
                self._back_button()
                if self.pinned:
                    self._pin_close_button()
                self.popup_at(anchor)
                return
        if sticky is None:
            sticky = bool(QtWidgets.QApplication.keyboardModifiers()
                          & QtCore.Qt.ShiftModifier)
        try:
            model.set_last_fired(self.pie.name, cmd)
        except Exception:  # noqa: BLE001, S110 -- no params outside FreeCAD
            pass
        if sticky or self.pinned:
            self.fire(cmd)
            return
        self.close()
        self.fire(cmd)

    def back(self):
        """One step up the door trail."""
        if not self._stack:
            return
        anchor = self.mapToGlobal(
            QtCore.QPoint(int(self._origin[0]), int(self._origin[1])))
        self.build(self._stack.pop())
        self._back_button()
        self.popup_at(anchor)

    def _back_button(self):
        if not self._stack:
            return
        btn = QtWidgets.QToolButton(self)
        size = 24
        btn.setFixedSize(size, size)
        btn.setText("◂")
        # the pie's own chip look: readable on the canvas, consistent
        btn.setStyleSheet(f"QToolButton{{{self._base_css}"
                          f"border-radius:{size // 2}px;}}")
        btn.setToolTip(f"Back to {self._stack[-1]} (Backspace)")
        btn.move(int(self._origin[0] - size / 2),
                 int(self._origin[1] - size / 2))
        btn.clicked.connect(self.back)
        btn.setVisible(True)
        label = getattr(self, "_name_label", None)
        if label is not None:         # make room: name sits under the back
            label.move(int(self._origin[0] - label.width() / 2),
                       int(self._origin[1] + size / 2 + 2))

    def _pin_close_button(self):
        btn = QtWidgets.QToolButton(self)
        btn.setText("✕")
        btn.setStyleSheet(f"QToolButton{{{self._base_css}"
                          "border-radius:4px;}")
        btn.setToolTip("Unpin")
        btn.adjustSize()
        btn.move(self.width() - btn.width() - 2, 2)
        btn.clicked.connect(self.close)
        btn.setVisible(True)

    def refresh_counts(self, counts):
        """Pinned palettes follow the selection: rebuild in place."""
        self.counts = counts
        self.build(self.pie.name)
        self._pin_close_button()

    def closeEvent(self, event):
        if self.pinned:
            if self._rt is not None:
                self._rt.unregister_pin(self)
            self.deleteLater()        # palettes are throwaway children
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if self.pinned:
            self._drag_at = event.position().toPoint() \
                if hasattr(event, "position") else event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.pinned and self._drag_at is not None:
            self._drag_at = None
            self._snap_to_edge()
        super().mouseReleaseEvent(event)

    def _snap_to_edge(self):
        """Dropped near an edge of the main window, a palette rests flush
        against it (and then tucks itself away when the mouse leaves)."""
        parent = self.parentWidget()
        if parent is None:
            self._snapped_edge = None
            return
        margin, geo = 28, self.geometry()
        edges = {"left": geo.x(),
                 "top": geo.y(),
                 "right": parent.width() - geo.x() - geo.width(),
                 "bottom": parent.height() - geo.y() - geo.height()}
        edge = min(edges, key=edges.get)
        if edges[edge] > margin:
            self._snapped_edge = None
            return
        self._snapped_edge = edge
        if edge == "left":
            self.move(2, geo.y())
        elif edge == "right":
            self.move(parent.width() - geo.width() - 2, geo.y())
        elif edge == "top":
            self.move(geo.x(), 2)
        else:
            self.move(geo.x(), parent.height() - geo.height() - 2)

    def leaveEvent(self, event):
        if self.pinned and self._snapped_edge and not self._collapsed:
            self._collapse()
        super().leaveEvent(event)

    def enterEvent(self, event):
        if self._collapsed:
            self._expand()
        super().enterEvent(event)

    def _collapse(self):
        """A snapped palette folds to a slim tab; hovering it reopens."""
        self._collapsed = True
        self._expanded_geo = self.geometry()
        for child in self.findChildren(QtWidgets.QWidget):
            child.setVisible(False)
        parent, geo = self.parentWidget(), self._expanded_geo
        if self._snapped_edge in ("left", "right"):
            tab = QtCore.QRect(0, geo.y(), 14, min(geo.height(), 120))
            if self._snapped_edge == "right":
                tab.moveLeft(parent.width() - 14)
        else:
            tab = QtCore.QRect(geo.x(), 0, min(geo.width(), 120), 14)
            if self._snapped_edge == "bottom":
                tab.moveTop(parent.height() - 14)
        self.setGeometry(tab)

    def _expand(self):
        self._collapsed = False
        if self._expanded_geo is not None:
            self.setGeometry(self._expanded_geo)
        self.build(self.pie.name)
        self._pin_close_button()

    def show_hint(self, text):
        """The binding that opened this pie, shown while it is still new."""
        label = HaloLabel(text, self, "#999", 10)
        label.adjustSize()
        label.move(int(self._origin[0] - label.width() / 2),
                   self.height() - label.height() - 2)
        label.setVisible(True)

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text().upper()
        if len(text) == 1 and text.isalpha():
            # a slot's own letter fires it — and deliberately outranks
            # the built-in P-to-pin when a slot claimed P
            for btn in self.buttons:
                if btn.property("accel") == text \
                        and btn.isEnabled() and not btn.isHidden():
                    btn.click()
                    return
        if QtCore.Qt.Key_1 <= key <= QtCore.Qt.Key_9:
            index = key - QtCore.Qt.Key_1
            if index < len(self.buttons):
                btn = self.buttons[index]
                if btn.isEnabled() and not btn.isHidden():
                    btn.click()
                    return
        if key == QtCore.Qt.Key_Backspace and self._stack:
            self.back()
            return
        if key == QtCore.Qt.Key_P and not self.pinned \
                and self._rt is not None:
            at = self.mapToGlobal(QtCore.QPoint(int(self._origin[0]),
                                                int(self._origin[1])))
            self.close()              # release the popup grab first
            self._rt.pin_pie(self.pie.name, at)
            return
        if key == QtCore.Qt.Key_Escape and self.pinned:
            self.close()
            return
        super().keyPressEvent(event)

    def popup_at(self, global_pos):
        top_left = QtCore.QPoint(int(global_pos.x() - self._origin[0]),
                                 int(global_pos.y() - self._origin[1]))
        parent = self.parentWidget()
        if parent is not None:        # pinned palette inside the main window
            top_left = parent.mapFromGlobal(top_left)
            top_left.setX(max(0, min(top_left.x(),
                                     parent.width() - self.width())))
            top_left.setY(max(0, min(top_left.y(),
                                     parent.height() - self.height())))
        else:
            # a pie at the screen edge shifts fully on-screen; the hand
            # is warped by the same shift so aim still starts centred
            # (a no-op on Wayland, where clamping alone still helps)
            screen = QtGui.QGuiApplication.screenAt(global_pos) \
                or QtWidgets.QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                clamped = QtCore.QPoint(
                    max(avail.left(),
                        min(top_left.x(), avail.right() - self.width())),
                    max(avail.top(),
                        min(top_left.y(), avail.bottom() - self.height())))
                delta = clamped - top_left
                if not delta.isNull():
                    top_left = clamped
                    cursor = QtGui.QCursor.pos()
                    # mid-stroke (hand already away from the anchor) a
                    # warp would corrupt the gesture: skip it
                    if (cursor - global_pos).manhattanLength() < 40:
                        QtGui.QCursor.setPos(cursor + delta)
        self.move(top_left)
        self.show()

    def nearest_slot(self, global_pos):
        """The slot the position aims at. Circle pies read a direction:
        the radius picks the ring, the angle picks the slot within it,
        so the same direction resolves the same at any reach. Grids stay
        nearest-by-distance. Disabled and empty slots take part: aiming
        at one is a deliberate no-op the caller must honour, never a
        pass-through to the enabled neighbour."""
        if self._sectors:
            return self._angular_slot(global_pos)
        best, dist = None, None
        for btn in self.buttons:
            if not btn.isVisible():          # hidden = empty slot
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

    def _angular_slot(self, global_pos):
        """Direction-first resolution with ~5 degrees of stickiness for
        the slot already resolved, so sector boundaries don't flutter."""
        origin = self.mapToGlobal(QtCore.QPoint(int(self._origin[0]),
                                                int(self._origin[1])))
        dx = global_pos.x() - origin.x()
        dy = global_pos.y() - origin.y()
        reach = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        rings = {}
        for ring, radius, angle, btn in self._sectors:
            rings.setdefault(ring, []).append((angle, radius, btn))
        radii = {ring: sum(s[1] for s in slots) / len(slots)
                 for ring, slots in rings.items()}
        outer = max(radii.values())
        # the ring the reach points at; past the outer ring IS the outer
        # ring -- a fling keeps its direction at any length
        band = min(radii, key=lambda r: abs(radii[r] - min(reach, outer)))
        slots = rings[band]

        def delta(angle):
            d = abs(angle - theta) % (2 * math.pi)
            return min(d, 2 * math.pi - d)

        if len(slots) > 1:
            ordered = sorted(a for a, _r, _b in slots)
            gaps = [b - a for a, b in itertools.pairwise(ordered)]
            gaps.append(2 * math.pi - (ordered[-1] - ordered[0]))
            half = max(min(gaps) / 2, math.radians(6))
        else:
            half = math.pi / 2
        stick = math.radians(5)
        best_angle, _r, best = min(slots, key=lambda s: delta(s[0]))
        if self._aim_stick is not None and self._aim_stick is not best:
            for angle, _radius, btn in slots:
                if btn is self._aim_stick and delta(angle) <= half + stick:
                    best_angle, best = angle, btn   # incumbent keeps it
                    break
        margin = stick if best is self._aim_stick else 0.0
        if delta(best_angle) > half + margin:
            self._aim_stick = None       # outside every sector (arc pies)
            return None
        self._aim_stick = best
        return best

    def _set_aim(self, btn):
        """Live feedback for the gesture: ring the slot the aim resolves
        to, and say at the centre what release will do."""
        shown = btn if btn is not None and btn.isVisible() else None
        target = shown if shown is not None and shown.isEnabled() else None
        if target is not self._aimed:
            for widget, state in ((self._aimed, False), (target, True)):
                if widget is not None:
                    widget.setProperty("aimed", state)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
            self._aimed = target
        label = getattr(self, "_name_label", None)
        if label is None:
            return
        if btn is None:
            text = "Cancel"              # the dead zone: aim withdrawn
        elif shown is None:
            text = "—"                   # an empty sector: nothing here
        else:
            text = shown.property("aimname") or ""
            if not shown.isEnabled():
                text += " — unavailable"
        if text != label.text():
            centre = label.geometry().center()
            label.setText(text)
            label.adjustSize()
            geo = label.geometry()
            geo.moveCenter(centre)
            label.move(geo.topLeft())

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
        if btn is None or not btn.isEnabled():
            self.close()     # nothing aimed, or a dead slot: run nothing
            return
        btn.click()

    # -- the gesture arrow (release mode): centre -> cursor

    def mouseMoveEvent(self, event):
        if self.pinned and self._drag_at is not None \
                and event.buttons() & QtCore.Qt.LeftButton:
            # local delta onto the current position: works the same for a
            # child of the main window and a real window, no globals
            here = event.position().toPoint() \
                if hasattr(event, "position") else event.pos()
            self.move(self.pos() + here - self._drag_at)
            return
        if self.run_mode == "release":
            self._aim = event.position().toPoint() \
                if hasattr(event, "position") else event.pos()
            spot = self.mapToGlobal(self._aim)
            dx = self._aim.x() - self._origin[0]
            dy = self._aim.y() - self._origin[1]
            beyond = (dx * dx + dy * dy) ** 0.5 \
                >= max(24, self.pie.radius * 0.45)
            over = self.nearest_slot(spot) if beyond else None
            self._set_aim(over)
            self.update()
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._opaque and not self._collapsed:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(
                self.palette().color(QtGui.QPalette.Mid), 1))
            painter.setBrush(self._panel_color
                             or self.palette().window())
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1),
                                    10, 10)
            painter.end()
        if self._collapsed:
            # the folded palette is just a slim tab on the window edge
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(self._accent, 1))
            painter.setBrush(self.palette().button())
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                                    5, 5)
            return
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
        color = custom_color("ArrowColor") or self._accent
        # minimal: one thin solid line, one small solid head
        ux, uy = (p2.x() - p1.x()) / length, (p2.y() - p1.y()) / length
        nx, ny = -uy, ux
        head = min(11.0, length * 0.3)
        neck = QtCore.QPointF(p2.x() - ux * head, p2.y() - uy * head)
        painter.setPen(QtGui.QPen(color, 2, QtCore.Qt.SolidLine,
                                  QtCore.Qt.RoundCap))
        painter.drawLine(QtCore.QLineF(p1, neck))
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QtGui.QPolygonF([
            p2,
            QtCore.QPointF(neck.x() + nx * 4.5, neck.y() + ny * 4.5),
            QtCore.QPointF(neck.x() - nx * 4.5, neck.y() - ny * 4.5)]))
        painter.end()


class _DwellRing(QtWidgets.QWidget):
    """A fill tracing the button's outline: time until it activates."""

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
        pie_widget = self.parentWidget().parentWidget() \
            if self.parentWidget() else None
        color = getattr(pie_widget, "_accent", None) or accent()
        painter.setPen(QtGui.QPen(color, 3,
                                  QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        # trace the button's actual shape, not a forced circle
        rect = QtCore.QRectF(self.rect().adjusted(2, 2, -2, -2))
        pie = getattr(pie_widget, "pie", None)
        radius = min(rect.height() / 2,
                     shape_radius(pie) if pie is not None
                     else rect.height() / 2)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        steps = 48
        points = [path.pointAtPercent(min(0.999,
                                          self.progress * k / steps))
                  for k in range(steps + 1)]
        painter.drawPolyline(QtGui.QPolygonF(points))
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
    _watch_chooser(self, self._chooser, btn)


def _watch_chooser(widget, chooser, btn, misses_limit=3):
    """The flyout goes away by itself ~750ms after the cursor has left
    both it and its slot; hovering back in resets the clock."""
    timer = QtCore.QTimer(chooser)     # dies with the chooser
    timer.setInterval(250)
    state = {"misses": 0}

    def tick():
        if widget._chooser is not chooser or not chooser.isVisible():
            timer.stop()
            return
        pos = QtGui.QCursor.pos()
        over = chooser.rect().adjusted(-8, -8, 8, 8).contains(
            chooser.mapFromGlobal(pos)) \
            or btn.rect().contains(btn.mapFromGlobal(pos))
        if over:
            state["misses"] = 0
            return
        state["misses"] += 1
        if state["misses"] >= misses_limit:
            timer.stop()
            chooser.deleteLater()
            widget._chooser = None

    timer.timeout.connect(tick)
    timer.start()


PieWidget.show_chooser = _show_chooser


class _StrokeGhost(QtWidgets.QWidget):
    """The 300ms mark trace: a line from press to release, then gone."""

    def __init__(self, parent, start, end):
        super().__init__(parent)
        self._start = start
        self._end = end
        pad = 8
        left = min(start.x(), end.x()) - pad
        top = min(start.y(), end.y()) - pad
        self.setGeometry(left, top,
                         abs(start.x() - end.x()) + 2 * pad,
                         abs(start.y() - end.y()) + 2 * pad)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.show()
        self.raise_()
        QtCore.QTimer.singleShot(300, self.deleteLater)

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        color = accent()
        painter.setPen(QtGui.QPen(color, 3, QtCore.Qt.SolidLine,
                                  QtCore.Qt.RoundCap))
        a = self.mapFromParent(self._start)
        b = self.mapFromParent(self._end)
        painter.drawLine(a, b)
        painter.setBrush(color)
        painter.drawEllipse(b, 4, 4)


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
    STUCK_MS = 2000               # no key-up AND no motion by then = stuck

    def __init__(self, opener, gestures, fallback=None, mode_of=None,
                 fire=None, blind=None, parent=None):
        super().__init__(parent)
        self.opener = opener          # opener(name, at, hint, mode)
        self.gestures = gestures      # gestures(key) -> {gesture: pie_name}
        self.fallback = fallback or (lambda: None)   # the right-click pie
        self.mode_of = mode_of or (lambda name: "click")   # pie's run_on
        self.fire = fire or (lambda cmd: None)   # for Run: bind targets
        self.blind = blind            # blind(name, at, release) mark-ahead
        self.trace = deque(maxlen=12)  # recent dispatches, for the Doctor
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
        # some devices (MX Master, many Bluetooth and pen buttons) never
        # deliver a key-up: with no release and no motion, demote the
        # pie to click mode instead of waiting forever
        self._stuck = QtCore.QTimer(self)
        self._stuck.setSingleShot(True)
        self._stuck.setInterval(self.STUCK_MS)
        self._stuck.timeout.connect(self._keyup_guard)
        self._still_at = None         # cursor at the last stuck-check

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
        key, _quick, held, _qh, held_hint = self._deferred
        self._deferred = None
        if self.held == key and held is not None:
            if model.is_run(held):    # a held single command just runs
                self.close()
                self.fire(model.run_target(held))
                self.trace.append(
                    f"{key}: hold ran {model.run_target(held)}")
                return
            # the hand is still down: the held outcome, anchored at the
            # press point so movement so far counts as aim — and a hold
            # ALWAYS runs as a marking menu
            self.open_pie(held, at=self._press_pos, hint=held_hint,
                          mode="release")
            self.trace.append(f"{key}: hold opened {held} (marking)")
            self.held = key           # open_pie's close() cleared it

    def open_pie(self, name, at=None, hint="", mode=None):
        self.close()
        self.current = self.opener(name, at, hint, mode)
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
        if etype in (QtCore.QEvent.MouseButtonPress,
                     QtCore.QEvent.MouseButtonDblClick):
            # a fast double sends DblClick instead of a second Press; our
            # own double window does the counting, so both mean "down"
            name = MOUSE_KEYS.get(event.button())
            if name is not None and not self._typing_focus() \
                    and self.gestures(name):
                return self._press(name)
        if etype == QtCore.QEvent.MouseButtonRelease:
            name = MOUSE_KEYS.get(event.button())
            if name is not None and self.held == name:
                return self._release(name)
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
        return self._press(self._key_of(event))

    def _keyup_guard(self):
        if self.held is None:
            return
        # stillness is measured tick-to-tick, not since the press: the
        # screen-clamp warp (and ordinary aiming) moves the cursor once,
        # then a truly stuck key sits still for a whole interval
        pos = QtGui.QCursor.pos()
        anchor = self._still_at if self._still_at is not None \
            else self._press_pos
        if (pos - anchor).manhattanLength() > 10:
            self._still_at = pos
            self._stuck.start()   # a hand mid-aim is not a stuck key
            return
        self.held = None
        widget = self.current
        if widget is not None and widget.isVisible() \
                and getattr(widget, "run_mode", "") == "release":
            widget.run_mode = "click"   # stays for the mouse instead
            self.trace.append("no key-up arrived: pie demoted to click")

    def _press(self, key):
        gmap = self.gestures(key)
        if not gmap:
            return False
        self._press_pos = QtGui.QCursor.pos()
        self._still_at = None
        self._stuck.start()
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
        quick_hint = f"{key} ··" if double_ready else f"{key} ·"
        held_hint = f"{key} ··—" if double_ready else f"{key} —"
        ambiguous = held is not None and held != quick
        if not ambiguous and not double_ready and quick is not None \
                and self.mode_of(quick) == "release" \
                and ("double" in gmap or "double-hold" in gmap):
            # a gesture pie ahead of a possible double: wait it out so a
            # quick tap is a no-op and a double-tap never flickers
            held = quick
            held_hint = quick_hint
            ambiguous = True
        if not ambiguous:
            name = quick if quick is not None else held
            if model.is_run(name):
                # a single bound command: fires right away, and a fast
                # second tap just fires it again
                self.close()
                self.fire(model.run_target(name))
                self.trace.append(
                    f"{key}: press ran {model.run_target(name)}")
                self.held = key
                return True
            if self._reuse(name):
                # the same pie is already up: a persistent pie toggles shut
                # (only when this key has no other gesture to protect)
                if (self.mode_of(name) != "release"
                        and behaviour()["toggle"] and set(gmap) <= {"press"}):
                    self.close()
                    return True
            else:
                self.open_pie(name, hint=quick_hint)
                self.trace.append(f"{key}: opened {name}")
            self.held = key
            return True
        # ambiguous: hold (or movement) opens the held pie; an early
        # release resolves to the quick one
        self._deferred = (key, quick, held, quick_hint, held_hint)
        self._press_pos = QtGui.QCursor.pos()
        self._defer.start()
        self.held = key
        return True

    def _key_release(self, event):
        if self.held is None:
            return False
        if self._key_of(event) != self.held:
            return False
        return self._release(self.held)

    def _release(self, _key):
        self._stuck.stop()
        self.held = None
        if self._deferred is not None:
            # released before the held outcome could open
            _key, quick, held, quick_hint, held_hint = self._deferred
            self._defer.stop()
            self._deferred = None
            release = QtGui.QCursor.pos()
            moved = (release - self._press_pos).manhattanLength() > 24
            if moved and held is not None and not model.is_run(held):
                # motion means a gesture: the whole stroke finished
                # before the pie ever rendered, so resolve it blind and
                # fire (mark-ahead); when that can't — a door with no
                # stroke past it, a dead sector — show the pie instead
                if self.blind is not None \
                        and self.blind(held, self._press_pos, release):
                    self.trace.append(f"{_key}: mark-ahead fired ({held})")
                    return True
                self.open_pie(held, at=self._press_pos, hint=held_hint)
                self.trace.append(f"{_key}: stroke fell back to {held}")
                return True
            # a still tap
            if quick is not None and model.is_run(quick):
                self.close()
                self.fire(model.run_target(quick))
                self.trace.append(
                    f"{_key}: tap ran {model.run_target(quick)}")
                return True
            if quick is not None and self.mode_of(quick) != "release" \
                    and not self._reuse(quick):
                # a persistent quick pie opens where the press happened;
                # a release pie on a completed tap means nothing at all
                self.open_pie(quick, at=self._press_pos, hint=quick_hint)
                self.trace.append(f"{_key}: tap opened {quick}")
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
            if model.is_run(name):
                self.fire(model.run_target(name))
            else:
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


def _flush_params():
    try:
        App.saveParameter()
    except Exception:  # noqa: BLE001 -- older builds save on exit only
        return


class _SelectionWatch:
    """Feeds selection changes to the runtime (debounced there)."""

    def __init__(self, rt):
        self.rt = rt

    def addSelection(self, *_args):
        self.rt._selection_poke()

    def removeSelection(self, *_args):
        self.rt._selection_poke()

    def setSelection(self, *_args):
        self.rt._selection_poke()

    def clearSelection(self, *_args):
        pass


class Runtime:
    def __init__(self, gui):
        self.gui = gui
        self.pies = {}
        self.binds = {}
        self._keys = {}               # normalised key -> stored key
        self._registered = set()
        self._pinned = []             # floating palettes, refreshed on select
        self.open_preferences = None  # wired by InitGui once the dialog exists
        self.dispatcher = Dispatcher(
            self._open_for_dispatch, self._gestures,
            fallback=lambda: self._resolve(None),
            mode_of=lambda n: self.pies[n].run_on if n in self.pies
            else "click",
            fire=self.fire, blind=self.blind_fire)
        self._sel_observer = _SelectionWatch(self)
        self._sel_timer = QtCore.QTimer()
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(200)
        self._sel_timer.timeout.connect(self._selection_settled)
        # FreeCAD only writes user.cfg on a clean exit; flush shortly after
        # activity so stats and edits survive crashes and kills too
        self._save_timer = QtCore.QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(4000)
        self._save_timer.timeout.connect(_flush_params)

    # -- model access

    def reload(self):
        _AVAILABLE["prefix"].clear()    # an addon may have just arrived
        _AVAILABLE["cmd"].clear()
        self.pies = model.load_pies()   # a saved Smart carries its settings
        self.binds = model.load_binds()
        self._keys = {}
        for scope in self.binds.values():
            for key in scope:
                if key in MOUSE_KEYS.values():
                    self._keys[key] = key    # not a key sequence
                else:
                    self._keys[QtGui.QKeySequence(key).toString()] = key
        self._register_commands()
        self._save_timer.start()     # edits survive a killed session too

    def _register_commands(self):
        for name in dict.fromkeys(list(self.pies) + [model.SMART_NAME]):
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

    def _is_workbench(self, cmd):
        lister = getattr(self.gui, "listWorkbenches", None)
        try:
            return lister is not None and cmd in lister()
        except Exception:  # noqa: BLE001 -- half-built Gui
            return False

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

    def _open_for_dispatch(self, name, at=None, hint="", mode=None):
        return self.open_pie(name, at, hint, mode=mode)

    def _pies_for(self, name):
        if name != model.SMART_NAME:
            return self.pies
        # contents rebuilt every open: your most used tools, here, now,
        # weighted by what is selected; layout and behaviour come from
        # the saved Smart pie, if any
        pies = dict(self.pies)
        pies[model.SMART_NAME] = model.smart_pie(
            workbench_scope(self.gui),
            base=self.pies.get(model.SMART_NAME),
            counts=self.counts())
        return pies

    def open_pie(self, name, at=None, hint="", mode=None):
        pies = self._pies_for(name)
        if name not in pies:
            return None
        widget = PieWidget(pies, name, self.counts(), self.fire,
                           runtime=self, mode=mode)
        if hint:
            opens = model._grp(f"Pies/{name}").GetInt("Opens", 0) + 1
            model._grp(f"Pies/{name}").SetInt("Opens", opens)
            if opens <= 12:          # training wheels come off by themselves
                widget.show_hint(hint)
        widget.popup_at(at if at is not None and not at.isNull()
                        else QtGui.QCursor.pos())
        self.dispatcher.current = widget
        return widget

    def fire(self, cmd):
        try:
            if cmd.startswith(model.PANEL_PREFIX):
                # drives the task panel; not a tool, so not a statistic
                self._panel_action(cmd[len(model.PANEL_PREFIX):])
                return
            if cmd.startswith(model.MACRO_PREFIX):
                path = os.path.join(App.getUserMacroDir(True),
                                    cmd[len(model.MACRO_PREFIX):])
                self.gui.doCommand(
                    f"exec(open({path!r}).read())")
            elif self._is_workbench(cmd):
                # workbench entries are not commands: activate directly
                self.gui.activateWorkbench(cmd)
            else:
                self.gui.runCommand(cmd, 0)
            model.bump_stat(workbench_scope(self.gui), cmd,
                            axis=model.dominant_axis(self.counts()))
            self._save_timer.start()
        except Exception as exc:  # noqa: BLE001 -- a broken command must not kill the pie
            if App is not None:
                App.Console.PrintWarning(f"PieMenu: {cmd} failed: {exc}\n")

    def _panel_action(self, action):
        """Click OK/Apply/Cancel on the visible task panel, wherever it
        is docked; Cancel falls back to closing the task dialog."""
        getmw = getattr(self.gui, "getMainWindow", None)
        mw = getmw() if getmw is not None else None
        role = {"OK": QtWidgets.QDialogButtonBox.Ok,
                "Apply": QtWidgets.QDialogButtonBox.Apply,
                "Cancel": QtWidgets.QDialogButtonBox.Cancel}.get(action)
        if mw is not None and role is not None:
            for box in mw.findChildren(QtWidgets.QDialogButtonBox):
                if not box.isVisible():
                    continue
                btn = box.button(role)
                if btn is not None and btn.isVisible() and btn.isEnabled():
                    btn.click()
                    return
        if action == "Cancel":
            control = getattr(self.gui, "Control", None)
            if control is not None:
                control.closeDialog()

    # -- auto-open on selection (off unless the behaviour switch is on)

    def register_pin(self, widget):
        self._pinned.append(widget)

    def unregister_pin(self, widget):
        if widget in self._pinned:
            self._pinned.remove(widget)

    def blind_fire(self, name, at, release, depth=0):
        """Mark-ahead: resolve a completed stroke against the pie's
        geometry without ever showing it. A stroke that runs on past a
        door slot continues into that pie (a compound mark, up to three
        levels). True when a command actually fired."""
        pies = self._pies_for(name)
        if name not in pies:
            return False
        widget = PieWidget(pies, name, self.counts(), self.fire,
                           runtime=self, mode="release")
        try:
            widget.move(at.x() - int(widget._origin[0]),
                        at.y() - int(widget._origin[1]))
            btn = widget.nearest_slot(release)
            if btn is None or not btn.isEnabled():
                return False
            cmd = btn.property("cmd") or ""
            if is_pie_command(cmd):
                if depth >= 2:
                    return False
                anchor = btn.mapToGlobal(QtCore.QPoint(
                    btn.width() // 2, btn.height() // 2))
                past = (release - anchor).manhattanLength() > 24
                return past and self.blind_fire(
                    pie_target(cmd), anchor, release, depth + 1)
            btn.click()
            if depth == 0:
                self._stroke_ghost(at, release)
            return True
        finally:
            widget.deleteLater()

    def _stroke_ghost(self, start, end):
        """A brief static trace of the mark, so a blind fire is never a
        silent one. No animation: it appears, then it is gone."""
        getmw = getattr(self.gui, "getMainWindow", None)
        mw = getmw() if getmw is not None else None
        if mw is None:
            return
        try:
            _StrokeGhost(mw, mw.mapFromGlobal(start), mw.mapFromGlobal(end))
        except Exception:  # noqa: BLE001, S110 -- feedback must never break the fire
            pass

    def pin_pie(self, name, at=None):
        """A floating palette: tools fire without closing, conditional
        slots re-resolve as the selection changes, drag moves it, Esc or
        the ✕ closes. Built as its own widget with its final window role
        (inside the main window when there is one) -- re-flagging a live
        popup crashes under Wayland."""
        pies = self._pies_for(name)
        if name not in pies:
            return None
        parent = None
        getmw = getattr(self.gui, "getMainWindow", None)
        if getmw is not None:
            try:
                parent = getmw()
            except Exception:  # noqa: BLE001 -- half-built Gui
                parent = None
        widget = PieWidget(pies, name, self.counts(), self.fire,
                           runtime=self, parent=parent, pinned=True)
        widget.popup_at(at if at is not None and not at.isNull()
                        else QtGui.QCursor.pos())
        widget.raise_()
        self.register_pin(widget)
        return widget

    def watch_selection(self):
        try:
            import FreeCADGui as Gui
            Gui.Selection.addObserver(self._sel_observer)
        except Exception:  # noqa: BLE001 -- no Selection outside the GUI
            return

    def _selection_poke(self):
        if App is None:
            return
        if not self._pinned and not behaviour()["autoopen"]:
            return
        self._sel_timer.start()

    def _selection_settled(self):
        counts = self.counts()
        for widget in list(self._pinned):    # palettes follow the selection
            if widget.isVisible():
                widget.refresh_counts(counts)
        self._auto_open()

    def _auto_open(self):
        if not behaviour()["autoopen"]:
            return
        disp = self.dispatcher
        if disp.current is not None and disp.current.isVisible():
            return
        if disp._typing_focus():
            return
        name = self._resolve(None)
        if not name or name not in self.pies:
            return
        counts = self.counts()
        if not counts:
            return
        pie = self.pies[name]
        live = any(b.rule and model.match_rule(b.rule, counts)
                   for slot in pie.items for b in (slot or []))
        if live:
            self.open_pie(name)


def start(gui):
    """Install the v2 runtime: load the model, register commands and the
    app-wide dispatcher.  Called once from InitGui."""
    global runtime
    runtime = Runtime(gui)
    runtime.reload()
    runtime.watch_selection()
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.installEventFilter(runtime.dispatcher)
    return runtime
