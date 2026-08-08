"""The v2 preferences dialog, built to the mockup (mockups/preferences2.html).

Layout: a flat pie list · the preview (a union view: every slot with markers,
never a simulation) · the Slots table (every binding with its rule, edited in
place) · the settings column (sliders, ring readout, anchor cross, hover
help) — and underneath, the shortcuts table (key × workbench, the key and Any
columns pinned).  Doors, rules and scoped binds all edit the same model the
runtime reads; every change calls ``on_change`` so the caller can reload it.
"""

import json
import math
import os
import tempfile

from PySide import QtCore, QtGui, QtWidgets

try:
    import FreeCAD as App
except ImportError:
    App = None

from . import model, runtime
from .model import ANY_SCOPE, AXES, Binding, Pie, is_pie_command, pie_target

SIGNS = ("<", "<=", "==", "!=", ">", ">=")

HELP = {
    "Family": "Circle arranges the slots around the cursor; grid stacks them "
              "into blocks. These two replace the eleven old shapes.",
    "Slots": "How many positions this pie has. Empty slots stay empty — tools "
             "no longer fill positions in list order.",
    "Rings": "How rings fill. Uniform: the same count each ring. Auto: as "
             "many as each ring's circumference fits, so outer rings hold "
             "more. Custom: set every ring yourself.",
    "Per ring": "How many slots go in each ring before a new one starts "
                "further out. In custom mode, comma-separated counts — "
                "8,16 — with the last number repeating outward.",
    "Radius": "Distance from the cursor to the first ring.",
    "Arc": "How much of the circle the slots span. 360 is the full circle.",
    "Facing": "Which way a partial arc points. A 90° arc facing right sits "
              "either side of the 3 o'clock line.",
    "Stagger": "Push every other slot outward (or inward), so neighbours are "
               "easier to tell apart.",
    "Stagger by": "How far the alternate slots move, in pixels. Negative "
                  "pulls them inward.",
    "Columns": "Slots across, per block.",
    "Rows": "Slots down, per block.",
    "Anchors": "Which sides of the cursor carry a block — toggle several for "
               "a block per side. Slots fill Top, Left, Center, Right, "
               "Bottom in that order.",
    "Offset": "Gap between the cursor and each block.",
    "Button": "Size of each slot, in pixels.",
    "Shape": "The slot buttons' shape: rounded corners, hard squares, "
             "squircles or full circles.",
    "Style": "How buttons are painted: flat fill, a subtle vertical "
             "gradient, or outline-only.",
    "Spacing": "Gap between neighbouring slots.",
    "Run on": "How a tool fires once the pie is open. Release is the marking-"
              "menu gesture: flick and let go.",
    "Delay": "Milliseconds before a hover fires a tool, opens a chooser pick "
             "or descends into a door.",
    "Chooser size": "Size of the buttons in the little overload menu, in "
                    "pixels.",
    "Doors on hover": "Dwelling on a door slot for the delay opens that pie "
                      "at the cursor — glide in, aim, release.",
    "Command names": "Write each tool's name in its slot as well as its icon.",
}


def rule_text(rule):
    if not rule:
        return "always"
    return " · ".join(f"{a} {s} {v}" for a in AXES
                      for s, v in ([rule[a]] if a in rule else []))


def doors_into(pies, name):
    """Every (pie, slot, rule) whose binding opens *name* — Opened by."""
    out = []
    for p in pies.values():
        for i, slot in enumerate(p.items):
            for b in slot or []:
                if is_pie_command(b.cmd) and pie_target(b.cmd) == name:
                    out.append((p.name, i, b.rule))
    return out


def list_commands():
    """Command name -> QAction from the main window; the picker's source and
    the icon source, same as the v1 approach."""
    out = {}
    if App is None or not App.GuiUp:
        return out
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    if mw is None:
        return out
    for action in mw.findChildren(QtGui.QAction):
        name = action.objectName()
        if name and "_" in name and not action.icon().isNull():
            out[name] = action
    return out


def workbench_scopes():
    try:
        import FreeCADGui as Gui
        names = sorted({str(w).split("Workbench")[0]
                        for w in Gui.listWorkbenches()})
        names = [n for n in names if n and n != "None"]
    except Exception:  # noqa: BLE001 -- console mode / tests
        names = ["Assembly", "Draft", "Part", "PartDesign", "Sketcher"]
    if "Sketcher" in names:
        # editing a sketch is its own, more specific scope
        names.insert(names.index("Sketcher") + 1, model.SKETCH_EDIT_SCOPE)
    return names


def workbench_icon(scope):
    """The workbench's own icon for a scope name, or None."""
    return runtime.workbench_icon(scope)


def current_scope():
    """The active workbench's scope name, or None outside the GUI."""
    try:
        import FreeCADGui as Gui
        return runtime.workbench_scope(Gui)
    except Exception:  # noqa: BLE001 -- console mode / tests
        return None


_TIP_IMAGE_CACHE = {}


def _tip_image(key):
    """A small drawn illustration for the trickiest knobs, cached as a PNG
    (Qt tooltips render <img>, but do not animate, so stills not gifs)."""
    if key in _TIP_IMAGE_CACHE:
        return _TIP_IMAGE_CACHE[key]
    painters = {"Arc": _draw_arc, "Facing": _draw_facing,
                "Stagger": _draw_stagger, "Anchors": _draw_anchors}
    if key not in painters:
        _TIP_IMAGE_CACHE[key] = None
        return None
    import tempfile
    pm = QtGui.QPixmap(150, 100)
    pm.fill(QtGui.QColor(250, 250, 250))
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painters[key](painter)
    painter.end()
    path = os.path.join(tempfile.gettempdir(),
                        f"piemenu-tip-{key.lower()}.png")
    pm.save(path)
    _TIP_IMAGE_CACHE[key] = path
    return path


def _dots(painter, centre, radius, angles, color):
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(color)
    import math
    for a in angles:
        painter.drawEllipse(
            QtCore.QPointF(centre.x() + math.cos(a) * radius,
                           centre.y() + math.sin(a) * radius), 5, 5)


def _draw_arc(p):
    import math
    grey, blue = QtGui.QColor(190, 190, 190), QtGui.QColor(70, 130, 200)
    c = QtCore.QPointF(40, 50)
    _dots(p, c, 26, [i * math.pi / 4 for i in range(8)], blue)
    c2 = QtCore.QPointF(108, 50)
    _dots(p, c2, 26, [i * math.pi / 4 for i in range(8)], grey)
    _dots(p, c2, 26, [-math.pi / 2 + i * math.pi / 3 for i in range(4)], blue)
    p.setPen(QtGui.QColor(120, 120, 120))
    p.drawText(QtCore.QRectF(10, 82, 60, 16), "360")
    p.drawText(QtCore.QRectF(84, 82, 60, 16), "180 up")


def _draw_facing(p):
    import math
    blue = QtGui.QColor(70, 130, 200)
    c = QtCore.QPointF(75, 50)
    _dots(p, c, 30, [-math.pi / 4 + i * math.pi / 6 for i in range(4)], blue)
    p.setPen(QtGui.QPen(QtGui.QColor(200, 90, 60), 2))
    p.drawLine(QtCore.QPointF(75, 50), QtCore.QPointF(112, 50))
    p.drawLine(QtCore.QPointF(112, 50), QtCore.QPointF(104, 44))
    p.drawLine(QtCore.QPointF(112, 50), QtCore.QPointF(104, 56))


def _draw_stagger(p):
    import math
    blue = QtGui.QColor(70, 130, 200)
    c = QtCore.QPointF(75, 52)
    angles = [i * math.pi / 4 for i in range(8)]
    _dots(p, c, 24, angles[::2], blue)
    _dots(p, c, 36, angles[1::2], blue)


def _draw_anchors(p):
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(70, 130, 200))
    for x in range(3):                     # a block above the cursor
        p.drawRect(45 + x * 22, 14, 18, 14)
    for x in range(3):                     # and one below
        p.drawRect(45 + x * 22, 72, 18, 14)
    p.setBrush(QtGui.QColor(200, 90, 60))
    p.drawEllipse(QtCore.QPointF(75, 51), 4, 4)


COLOURS = [
    ("Accent", "AccentColor", "door rings, hover borders, dwell rings"),
    ("Outline", "OutlineColor", "slot button borders"),
    ("Fill", "FillColor", "slot button background"),
    ("Arrow", "ArrowColor", "the gesture arrow (defaults to Accent)"),
]


def colors_dialog(parent, on_change):
    """Per-part color overrides; empty = follow the FreeCAD theme."""
    p = App.ParamGet(runtime.MAIN)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Pie colors")
    form = QtWidgets.QFormLayout(dlg)

    def swatch_css(param):
        color = runtime.custom_color(param)
        return (f"background:{color.name()};" if color
                else "") + "min-width:70px;"

    for label, param, what in COLOURS:
        rowbox = QtWidgets.QHBoxLayout()
        pick = QtWidgets.QPushButton("theme" if not
                                     runtime.custom_color(param) else "")
        pick.setStyleSheet(swatch_css(param))
        pick.setToolTip(what)

        def choose(_=False, param=param, pick=pick):
            current = runtime.custom_color(param) or runtime.accent()
            color = QtWidgets.QColorDialog.getColor(
                current, dlg, "Pie color")
            if color.isValid():
                p.SetString(param, color.name())
                pick.setText("")
                pick.setStyleSheet(swatch_css(param))
                on_change()

        def reset(_=False, param=param, pick=pick):
            p.RemString(param)
            pick.setText("theme")
            pick.setStyleSheet(swatch_css(param))
            on_change()

        pick.clicked.connect(choose)
        clear = QtWidgets.QToolButton()
        clear.setText("✕")
        clear.setToolTip("Back to the theme color")
        clear.clicked.connect(reset)
        rowbox.addWidget(pick)
        rowbox.addWidget(clear)
        lab = QtWidgets.QLabel(label + ":")
        lab.setToolTip(what)
        form.addRow(lab, rowbox)

    close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    close.rejected.connect(dlg.reject)
    close.clicked.connect(dlg.accept)
    form.addRow(close)
    return dlg


TEMPLATES = {
    "PartDesign essentials": [
        "PartDesign_Pad", "PartDesign_Pocket", "PartDesign_Fillet",
        "PartDesign_Chamfer", "PartDesign_Revolution", "PartDesign_Hole",
        "PartDesign_Mirrored", "PartDesign_LinearPattern"],
    "Sketcher constraints": [
        "Sketcher_ConstrainCoincident", "Sketcher_ConstrainHorizontal",
        "Sketcher_ConstrainVertical", "Sketcher_ConstrainDistance",
        "Sketcher_ConstrainParallel", "Sketcher_ConstrainPerpendicular",
        "Sketcher_ConstrainTangent", "Sketcher_ConstrainEqual"],
    "View pack": [
        "Std_ViewFitAll", "Std_ViewFront", "Std_ViewTop", "Std_ViewRight",
        "Std_ViewIsometric", "Std_ViewScreenShot"],
}


PRESET_INDEX = ("https://raw.githubusercontent.com/imadnyc/"
                "PieMenu-presets/main/")


def missing_requirements(data):
    """Which of a preset's declared requirements this install lacks.

    Tolerates junk: a non-list requires, or non-string entries, count as
    nothing required rather than an error.
    """
    requires = data.get("requires")
    if not isinstance(requires, list):
        return []
    missing = []
    for req in requires:
        if not isinstance(req, str) or not req.strip():
            continue
        if req.startswith(model.MACRO_PREFIX):
            if not runtime.command_available(req):
                missing.append(req)
        elif not runtime.prefix_available(req):
            missing.append(req)
    return missing


def _fetch(url, timeout=8):
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def browse_presets_dialog(parent, import_file):
    """Community presets: fetch the shared repository's index, list it,
    install any entry. Sharing back is a PR to that repository."""
    import tempfile
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Community presets")
    lay = QtWidgets.QVBoxLayout(dlg)
    listing = QtWidgets.QListWidget()
    listing.setMinimumSize(460, 240)
    lay.addWidget(listing)
    note = QtWidgets.QLabel(
        'Share yours: PR a .piemenu.json to '
        '<a href="https://github.com/imadnyc/PieMenu-presets">'
        'PieMenu-presets</a>.')
    note.setOpenExternalLinks(True)
    note.setStyleSheet("color: gray;")
    lay.addWidget(note)
    buttons = QtWidgets.QHBoxLayout()
    install = QtWidgets.QPushButton("Install")
    install.setEnabled(False)
    buttons.addWidget(install)
    buttons.addStretch(1)
    close = QtWidgets.QPushButton("Close")
    close.clicked.connect(dlg.accept)
    buttons.addWidget(close)
    lay.addLayout(buttons)

    try:
        index = json.loads(_fetch(PRESET_INDEX + "index.json"))
        for entry in index.get("presets", []):
            requires = [r for r in entry.get("requires", [])
                        if not runtime.prefix_available(r)]
            text = f"{entry.get('name', '?')} — {entry.get('author', '?')}"
            if entry.get("description"):
                text += f"\n    {entry['description']}"
            if requires:
                text += f"\n    needs: {', '.join(requires)} (not installed)"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, entry.get("file", ""))
            listing.addItem(item)
        if not listing.count():
            listing.addItem("the repository has no presets yet")
    except Exception as exc:  # noqa: BLE001 -- offline is a normal state
        listing.addItem("couldn't reach the preset repository")
        listing.addItem(str(exc))

    listing.itemSelectionChanged.connect(lambda: install.setEnabled(
        bool(listing.selectedItems())
        and bool(listing.selectedItems()[0].data(QtCore.Qt.UserRole))))

    def do_install():
        item = listing.selectedItems()[0]
        rel = item.data(QtCore.Qt.UserRole)
        try:
            text = _fetch(PRESET_INDEX + rel)
        except Exception as exc:  # noqa: BLE001 -- network died mid-way
            QtWidgets.QMessageBox.warning(dlg, "Download failed", str(exc))
            return
        with tempfile.NamedTemporaryFile(
                "w", suffix=".piemenu.json", delete=False,
                encoding="utf-8") as fh:
            fh.write(text)
            temp_path = fh.name
        import_file(temp_path, source=PRESET_INDEX + rel)
        os.unlink(temp_path)

    install.clicked.connect(do_install)
    return dlg


def stats_dialog(parent):
    """Your top tools, here and everywhere, with a reset."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Usage")
    lay = QtWidgets.QVBoxLayout(dlg)
    wb = current_scope() or ANY_SCOPE
    for title, table in ((f"Top tools in {wb}", model.stats(wb)),
                         ("Top tools everywhere", model.stats())):
        box = QtWidgets.QGroupBox(title)
        form = QtWidgets.QVBoxLayout(box)
        ranked = sorted(table.items(), key=lambda kv: -kv[1])[:12]
        if not ranked:
            form.addWidget(QtWidgets.QLabel("nothing fired yet"))
        for cmd, count in ranked:
            form.addWidget(QtWidgets.QLabel(
                f"{count:>4} ×  {command_label(cmd)}"))
        lay.addWidget(box)
    buttons = QtWidgets.QHBoxLayout()
    reset = QtWidgets.QPushButton("Reset stats")
    reset.clicked.connect(lambda: (model.reset_stats(), dlg.accept()))
    buttons.addWidget(reset)
    buttons.addStretch(1)
    close = QtWidgets.QPushButton("Close")
    close.clicked.connect(dlg.accept)
    buttons.addWidget(close)
    lay.addLayout(buttons)
    return dlg


def keys_dialog(parent):
    """Every key the addon answers to, in one place."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Keys")
    lay = QtWidgets.QVBoxLayout(dlg)
    for title, rows in (
        ("While a pie is open", (
            ("1–9", "fire the numbered slot"),
            ("Shift + pick", "fire without closing, chain several tools"),
            ("Backspace", "back out of a sub-pie"),
            ("P", "pin the pie as a floating palette"),
            ("Esc / ✕", "close a pinned palette"),
            ("right-click a slot", "edit it here in the preferences"),
            ("hover a door slot", "glide into that pie"),
        )),
        ("Your bindings", (
            ("Mouse4 / Mouse5",
             "the spare mouse buttons bind like keys, all four gestures"),
            ("· tap  ·· double  — hold  ··— double-hold",
             "one key carries up to four pies (the table above)"),
            ("workbench beats Any workbench",
             "the more specific scope answers first"),
            ("SketchEdit beats Sketcher",
             "while a sketch is open for editing"),
            ("moving while a key is held",
             "opens the hold pie immediately, anchored at the press"),
        )),
    ):
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        for r, (key, what) in enumerate(rows):
            key_label = QtWidgets.QLabel(key)
            key_label.setStyleSheet("font-weight:600;")
            grid.addWidget(key_label, r, 0)
            grid.addWidget(QtWidgets.QLabel(what), r, 1)
        grid.setColumnStretch(1, 1)
        lay.addWidget(box)
    note = QtWidgets.QLabel(
        "Bound keys are answered by PieMenu before FreeCAD sees them "
        "(never while you are typing in a field), so pick keys FreeCAD "
        "does not already use. The starter set sits on F3–F9 and skips "
        "F1 (help), F2 (rename) and F5 (recompute) for exactly that "
        "reason. The shortcuts table marks a key that would shadow a "
        "FreeCAD shortcut with ⚠.")
    note.setWordWrap(True)
    note.setStyleSheet("color: gray;")
    lay.addWidget(note)
    buttons = QtWidgets.QHBoxLayout()
    buttons.addStretch(1)
    close = QtWidgets.QPushButton("Close")
    close.clicked.connect(dlg.accept)
    buttons.addWidget(close)
    lay.addLayout(buttons)
    return dlg


def _help_button(text):
    """A small ? whose tooltip carries what used to be an inline caption."""
    btn = QtWidgets.QToolButton()
    btn.setText("?")
    btn.setAutoRaise(True)
    btn.setToolTip(text)
    btn.setCursor(QtCore.Qt.WhatsThisCursor)
    return btn


def _panel(margin=6):
    """A framed panel, mockup-style: a visible line around each region."""
    frame = QtWidgets.QFrame()
    frame.setObjectName("pmPanel")
    frame.setStyleSheet(
        "#pmPanel{border:1px solid palette(mid);border-radius:4px;}")
    lay = QtWidgets.QVBoxLayout(frame)
    lay.setContentsMargins(margin, margin, margin, margin)
    return frame, lay


def command_icon(cmd, actions):
    if is_pie_command(cmd):
        return QtGui.QIcon(runtime.LOGO)
    action = actions.get(cmd)
    if action is not None and not action.icon().isNull():
        return action.icon()
    icon = runtime.command_icon(cmd)     # registry, loads the owning module
    return icon if icon is not None else QtGui.QIcon()


def command_label(cmd):
    if is_pie_command(cmd):
        return "▸ " + pie_target(cmd)
    if cmd.startswith(model.MACRO_PREFIX):
        return "◈ " + cmd[len(model.MACRO_PREFIX):].rsplit(".", 1)[0]
    if cmd.endswith("Workbench") and "_" not in cmd:
        return cmd[:-len("Workbench")]
    return cmd.split("_", 1)[-1]


def _list_macros():
    """The user's macro files, pickable as slot targets."""
    if App is None:
        return []
    try:
        folder = App.getUserMacroDir(True)
        return sorted(f for f in os.listdir(folder)
                      if f.lower().endswith((".fcmacro", ".py")))
    except Exception:  # noqa: BLE001 -- no macro dir is fine
        return []


GLYPH = {"press": "·", "double": "··", "hold": "—", "double-hold": "··—"}
GNAME = {"press": "press", "double": "double-press",
         "hold": "press-and-hold", "double-hold": "double-press-and-hold"}


# ---- rule editing ----------------------------------------------------------

class RuleField(QtWidgets.QWidget):
    """The v1-style chart: one row per axis — tick it, pick the sign, set
    the count.  Unticked axes don't constrain; nothing ticked = always."""

    changed = QtCore.Signal()

    def __init__(self, rule, parent=None):
        super().__init__(parent)
        self.rule = dict(rule)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 4)
        self.axis_rows = {}
        for r, axis in enumerate(AXES):
            tick = QtWidgets.QCheckBox(axis)
            sign = QtWidgets.QComboBox()
            sign.addItems(SIGNS)
            num = QtWidgets.QSpinBox()
            num.setRange(0, 99)
            if axis in self.rule:
                tick.setChecked(True)
                sign.setCurrentText(self.rule[axis][0])
                num.setValue(self.rule[axis][1])
            else:
                sign.setCurrentText(">=")
                num.setValue(1)
                sign.setEnabled(False)
                num.setEnabled(False)
            tick.toggled.connect(self._sync)
            sign.currentTextChanged.connect(self._sync)
            num.valueChanged.connect(self._sync)
            grid.addWidget(tick, r, 0)
            grid.addWidget(sign, r, 1)
            grid.addWidget(num, r, 2)
            self.axis_rows[axis] = (tick, sign, num)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)
        self.reads = QtWidgets.QLabel()
        self.reads.setStyleSheet("color: gray;")
        lay.addWidget(self.reads)
        self._render()

    def _sync(self, *_args):
        rule = {}
        for axis, (tick, sign, num) in self.axis_rows.items():
            on = tick.isChecked()
            sign.setEnabled(on)
            num.setEnabled(on)
            if on:
                rule[axis] = (sign.currentText(), num.value())
        self.rule = rule
        self._render()
        self.changed.emit()

    def _render(self):
        self.reads.setText("reads as: " + rule_text(self.rule))


def edit_rule(parent, binding, on_done):
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("When does this apply?")
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        f"{command_label(binding.cmd)} applies when:"))
    field = RuleField(binding.rule)
    lay.addWidget(field)
    bb = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        binding.rule = dict(field.rule)
        on_done()


# ---- the tool picker -------------------------------------------------------

class PickerDialog(QtWidgets.QDialog):
    """Search every workbench flat; the slot's current bindings shown while
    adding; the Pie menus group generated from the live pie list; the whole
    decision echoed before OK."""

    def __init__(self, pies, current_pie, slot, replace_binding=None,
                 actions=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose a tool or a pie")
        self.actions = list_commands() if actions is None else actions
        self.chosen = replace_binding.cmd if replace_binding else None
        lay = QtWidgets.QVBoxLayout(self)

        if slot and replace_binding is None:
            box = QtWidgets.QGroupBox("Already in this slot")
            form = QtWidgets.QVBoxLayout(box)
            for b in slot:
                row = QtWidgets.QLabel(
                    f"{command_label(b.cmd)}   —   {rule_text(b.rule)}")
                form.addWidget(row)
            lay.addWidget(box)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search every workbench…")
        self.search.textChanged.connect(self._rebuild)
        lay.addWidget(self.search)

        loader_row = QtWidgets.QHBoxLayout()
        loader_row.addWidget(QtWidgets.QLabel(
            "Missing a workbench's tools?"))
        self.bench_pick = QtWidgets.QComboBox()
        self.bench_pick.addItem("Load a workbench…")
        for wb in workbench_scopes():
            self.bench_pick.addItem(wb)
        self.bench_pick.activated.connect(self._load_bench)
        loader_row.addWidget(self.bench_pick)
        loader_row.addStretch(1)
        lay.addLayout(loader_row)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumSize(460, 260)
        self.tree.itemClicked.connect(self._picked)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.tree)

        lay.addWidget(QtWidgets.QLabel("Applies when:"))
        self.rule = RuleField(replace_binding.rule if replace_binding else {})
        self.rule.changed.connect(self._echo)
        lay.addWidget(self.rule)

        self.echo = QtWidgets.QLabel()
        lay.addWidget(self.echo)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._pies_ref, self._current_ref = pies, current_pie
        self._groups = self._grouped(pies, current_pie)
        self._rebuild()
        self._echo()
        self.search.setFocus()

    def _grouped(self, pies, current_pie):
        groups = {}
        for name in sorted(self.actions):
            groups.setdefault(name.split("_", 1)[0], []).append(name)
        doors = [model.PIE_PREFIX + p for p in sorted(pies)
                 if p != current_pie.name]
        doors.append(model.PIE_PREFIX + model.SMART_NAME)
        groups["Pie menus"] = doors
        macros = _list_macros()
        if macros:
            groups["Macros"] = [model.MACRO_PREFIX + m for m in macros]
        return groups

    def _load_bench(self, index):
        """Load a workbench so its commands (and icons) exist, then
        rescan; getWorkbench initialises it without the activation flash
        of switching there and back."""
        if index <= 0 or App is None or not App.GuiUp:
            return
        scope = self.bench_pick.itemText(index)
        try:
            import FreeCADGui as Gui
            benches = Gui.listWorkbenches()
            full = next((k for k in benches
                         if k.startswith(scope)), None)
            if full:
                Gui.getWorkbench(full)
        except Exception:  # noqa: BLE001 -- a bench that fails to load
            return
        self.actions = list_commands()
        self._groups = self._grouped(self._pies_ref, self._current_ref)
        self._rebuild()

    def _rebuild(self):
        query = self.search.text().strip().lower()
        self.tree.clear()
        for group, cmds in self._groups.items():
            hits = [c for c in cmds
                    if not query
                    or query in c.lower()
                    or query in command_label(c).lower()]
            if not hits:
                continue
            top = QtWidgets.QTreeWidgetItem([f"{group}  ({len(hits)})"])
            self.tree.addTopLevelItem(top)
            for cmd in hits:
                child = QtWidgets.QTreeWidgetItem([command_label(cmd)])
                child.setIcon(0, command_icon(cmd, self.actions))
                child.setData(0, QtCore.Qt.UserRole, cmd)
                top.addChild(child)
                if cmd == self.chosen:
                    self.tree.setCurrentItem(child)
            top.setExpanded(bool(query) or group == "Pie menus")

    def _picked(self, item, _col):
        cmd = item.data(0, QtCore.Qt.UserRole)
        if cmd:
            self.chosen = cmd
        self._echo()

    def _echo(self):
        if self.chosen:
            self.echo.setText(
                f"Adding:  {command_label(self.chosen)}  —  "
                + rule_text(self.rule.rule))
        else:
            self.echo.setText("Pick a tool or a pie above.")

    def result_binding(self):
        if not self.chosen:
            return None
        return Binding(self.chosen, dict(self.rule.rule))


# ---- preview ---------------------------------------------------------------

class PreviewWidget(QtWidgets.QWidget):
    """The union view: every slot drawn with markers (count badge, condition
    dot, door ring), never resolved.  Click selects, double-click picks,
    drag swaps."""

    slot_selected = QtCore.Signal(int)
    slot_activated = QtCore.Signal(int)
    slots_swapped = QtCore.Signal(int, int)
    slot_menu = QtCore.Signal(int, QtCore.QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pie = None
        self.actions = {}
        self.selected = 0
        self.highlight = -1
        self._drag_from = None
        self._mock_chooser = None    # (slot index, size): chooser-size demo
        self._stats = {}             # cmd -> fires, for never-used dimming
        self.setMinimumSize(420, 320)

    def flash_chooser(self, index, size):
        """Show a mock chooser under a slot, so the chooser-size knob has
        something visible to change. Stays until another pie is shown."""
        self._mock_chooser = (index, size)
        self.update()

    def _unflash(self):
        self._mock_chooser = None
        self.update()

    def set_pie(self, pie, actions):
        if pie is not self.pie:      # switching pies retires the chooser demo
            self._mock_chooser = None
        self.pie = pie
        self.actions = actions
        try:
            self._stats = model.stats()
        except Exception:  # noqa: BLE001 -- no params outside FreeCAD
            self._stats = {}
        self.update()

    def set_selected(self, index):
        self.selected = index
        self.update()

    def set_highlight(self, index):
        self.highlight = index
        self.update()

    def _geometry(self):
        pie = self.pie
        pos = model.positions(pie)
        if pie.show_names and len(pos) > 1:
            # spread like the live pie does, so full labels have room
            fm = self.fontMetrics()
            widest = max((fm.horizontalAdvance(command_label(s[0].cmd))
                          for s in pie.items if s), default=0) + 10
            if pie.family == "circle":
                step = pie.button + pie.spacing + 10
                chord = min(
                    2 * math.sin(math.pi / max(2, c))
                    * max(1, pie.radius + ring * step)
                    for ring, c in enumerate(model.ring_plan(pie, len(pos))))
                scale = max(1.0, widest / chord)
            else:
                scale = max(1.0, widest / (pie.button + pie.spacing))
            pos = [(x * scale, y * scale) for x, y in pos]
        cx, cy = self.width() / 2, self.height() / 2
        size = pie.button
        return [(int(cx + x - size / 2), int(cy + y - size / 2)) for x, y in pos]

    def slot_at(self, point):
        if self.pie is None:
            return None
        size = self.pie.button
        for i, (x, y) in enumerate(self._geometry()):
            if QtCore.QRect(x, y, size, size).contains(point):
                return i
        return None

    def paintEvent(self, _event):
        if self.pie is None:
            return
        pie = self.pie
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = self.palette()
        accent = pal.color(QtGui.QPalette.Highlight)
        size = pie.button
        tile_radius = {"square": 0, "rounded": 4,
                       "squircle": max(4, int(size * 0.32)),
                       "circle": size // 2}.get(pie.shape, 4)
        for i, (x, y) in enumerate(self._geometry()):
            rect = QtCore.QRect(x, y, size, size)
            slot = pie.items[i] if i < len(pie.items) else None
            if not slot:
                pen = QtGui.QPen(pal.color(QtGui.QPalette.Mid))
                pen.setStyle(QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRoundedRect(rect, tile_radius, tile_radius)
                painter.drawText(rect, QtCore.Qt.AlignCenter, "+")
            else:
                first = slot[0]
                door = is_pie_command(first.cmd)
                painter.setPen(QtGui.QPen(accent if door
                                          else pal.color(QtGui.QPalette.Mid),
                                          2 if door else 1))
                painter.setBrush(pal.color(QtGui.QPalette.Button))
                if door and pie.shape in ("rounded", "circle"):
                    painter.drawEllipse(rect)
                else:
                    painter.drawRoundedRect(rect, tile_radius, tile_radius)
                icon = command_icon(first.cmd, self.actions)
                never_used = (self._stats and not is_pie_command(first.cmd)
                              and first.cmd not in self._stats)
                if never_used:
                    painter.setOpacity(0.45)   # you have never fired this
                if icon.isNull():
                    painter.setPen(pal.color(QtGui.QPalette.ButtonText))
                    painter.drawText(rect, QtCore.Qt.AlignCenter,
                                     command_label(first.cmd)[:6])
                else:
                    icon.paint(painter, rect.adjusted(6, 6, -6, -6))
                painter.setOpacity(1.0)
                if pie.show_names:
                    painter.setPen(pal.color(QtGui.QPalette.ButtonText))
                    text = command_label(first.cmd)
                    tw = painter.fontMetrics().horizontalAdvance(text) + 8
                    below = QtCore.QRect(
                        rect.center().x() - tw // 2, rect.bottom() + 2,
                        tw, painter.fontMetrics().height())
                    # never off the edge of the preview
                    below.moveLeft(max(2, min(below.left(),
                                              self.width() - tw - 2)))
                    below.moveTop(min(below.top(),
                                      self.height() - below.height() - 2))
                    painter.drawText(below, QtCore.Qt.AlignCenter, text)
                conditional = any(b.rule for b in slot)
                if len(slot) > 1:
                    badge = QtCore.QRect(rect.right() - 9, rect.top() - 5,
                                         14, 14)
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(accent)
                    painter.drawEllipse(badge)
                    painter.setPen(pal.color(QtGui.QPalette.HighlightedText))
                    painter.drawText(badge, QtCore.Qt.AlignCenter,
                                     str(len(slot)))
                elif conditional:
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(accent)
                    painter.drawEllipse(rect.topLeft()
                                        + QtCore.QPoint(0, 0), 4, 4)
            if i == self.selected:
                painter.setPen(QtGui.QPen(accent, 2))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 6, 6)
            if i == self.highlight:
                painter.setPen(QtGui.QPen(accent, 3, QtCore.Qt.DotLine))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-5, -5, 5, 5), 8, 8)
        # the cursor anchor: where the pie opens relative to the hand
        painter.setPen(QtGui.QPen(pal.color(QtGui.QPalette.Mid), 1))
        painter.setBrush(pal.color(QtGui.QPalette.Mid))
        painter.drawEllipse(QtCore.QPoint(int(self.width() / 2),
                                          int(self.height() / 2)), 3, 3)
        if self._mock_chooser is not None:
            index, alt = self._mock_chooser
            geo = self._geometry()
            if index < len(geo):
                x, y = geo[index]
                slot = pie.items[index] if index < len(pie.items) else None
                count = max(2, len(slot or []))
                total = count * alt + (count - 1) * 2
                cx = int(x + size / 2 - total / 2)
                cy = int(y + size + 4)
                painter.setPen(QtGui.QPen(pal.color(QtGui.QPalette.Mid), 1))
                for j in range(count):
                    r = QtCore.QRect(cx + j * (alt + 2), cy, alt, alt)
                    painter.setBrush(pal.color(QtGui.QPalette.Button))
                    painter.drawRoundedRect(r, 3, 3)
                    if slot and j < len(slot):
                        icon = command_icon(slot[j].cmd, self.actions)
                        if not icon.isNull():
                            icon.paint(painter, r.adjusted(3, 3, -3, -3))
        painter.end()

    def mousePressEvent(self, event):
        index = self.slot_at(event.pos())
        if index is None:
            return
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_from = index
            self.slot_selected.emit(index)
        elif event.button() == QtCore.Qt.RightButton:
            self.slot_selected.emit(index)
            self.slot_menu.emit(index, event.globalPos())

    def mouseReleaseEvent(self, event):
        if self._drag_from is None:
            return
        target = self.slot_at(event.pos())
        if target is not None and target != self._drag_from:
            self.slots_swapped.emit(self._drag_from, target)
        self._drag_from = None

    def mouseDoubleClickEvent(self, event):
        index = self.slot_at(event.pos())
        if index is not None:
            self.slot_activated.emit(index)


def freecad_shortcuts():
    """Key text -> action label for every shortcut FreeCAD itself has, so
    the table can warn where a pie key would shadow one."""
    if App is None or not App.GuiUp:
        return {}
    try:
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
        action_type = getattr(QtGui, "QAction", None) \
            or QtWidgets.QAction
        out = {}
        for act in mw.findChildren(action_type):
            seq = act.shortcut().toString()
            if seq:
                label = act.text().replace("&", "") or act.objectName()
                out.setdefault(seq, label)
        return out
    except Exception:  # noqa: BLE001 -- half-built Gui
        return {}


# ---- the shortcuts table ---------------------------------------------------

class ShortcutsTable(QtWidgets.QWidget):
    """key × workbench, the key and Any columns pinned left.  Cells show the
    resolved pie: own binds solid, inherited from Any italic and dim."""

    changed = QtCore.Signal()
    jump_to_pie = QtCore.Signal(str)

    def __init__(self, workbenches=None, parent=None):
        super().__init__(parent)
        self.binds = {}
        self.pies = {}
        self.workbenches = workbenches or workbench_scopes()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.left = QtWidgets.QTableWidget(0, 1)
        self.left.setHorizontalHeaderLabels(["Any workbench"])
        self.left.verticalHeader().setSectionsClickable(True)
        self.left.setFixedWidth(240)
        self.left.horizontalHeader().setStretchLastSection(True)
        self.left.verticalHeader().sectionDoubleClicked.connect(self._rekey)
        self.left.verticalHeader().setContextMenuPolicy(
            QtCore.Qt.CustomContextMenu)
        self.left.verticalHeader().customContextMenuRequested.connect(
            self._key_menu)
        self.right = QtWidgets.QTableWidget(0, len(self.workbenches))
        self.right.setHorizontalHeaderLabels(self.workbenches)
        for col, wb in enumerate(self.workbenches):
            icon = workbench_icon(wb)
            hdr = self.right.horizontalHeaderItem(col)
            if icon is not None and hdr is not None:
                hdr.setIcon(icon)
        self.right.verticalHeader().setVisible(False)
        for table in (self.left, self.right):
            table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.cellDoubleClicked.connect(
                lambda row, col, t=table: self._bind_cell(t, row, col))
            table.cellClicked.connect(
                lambda row, col, t=table: self._jump(t, row, col))
        self.right.verticalScrollBar().valueChanged.connect(
            self.left.verticalScrollBar().setValue)
        self.left.verticalScrollBar().valueChanged.connect(
            self.right.verticalScrollBar().setValue)
        lay.addWidget(self.left)
        lay.addWidget(self.right, 1)

    # -- data

    def keys(self):
        keys = set()
        for scope in self.binds.values():
            keys.update(scope)
        return sorted(keys)

    def rebuild(self, pies, binds):
        self.pies = pies
        self.binds = binds
        keys = self.keys()
        clashes = freecad_shortcuts()
        for table in (self.left, self.right):
            table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            header = QtWidgets.QTableWidgetItem(key)
            if key in clashes:
                header.setText(f"{key} ⚠")
                header.setToolTip(
                    f"Also a FreeCAD shortcut: {clashes[key]}. "
                    "The pie answers first, so that command loses "
                    "this key.")
            self.left.setVerticalHeaderItem(row, header)
            self.left.setItem(row, 0, self._cell(key, ANY_SCOPE))
            self.left.setCellWidget(row, 0, self._cell_label(key, ANY_SCOPE))
            for col, wb in enumerate(self.workbenches):
                self.right.setItem(row, col, self._cell(key, wb))
                self.right.setCellWidget(row, col,
                                         self._cell_label(key, wb))
        self.right.resizeColumnsToContents()
        self.right.horizontalHeader().setMinimumSectionSize(96)
        for table in (self.left, self.right):
            table.resizeRowsToContents()
        for row in range(len(keys)):     # multi-gesture rows must line up
            h = max(self.left.rowHeight(row), self.right.rowHeight(row))
            self.left.setRowHeight(row, h)
            self.right.setRowHeight(row, h)
        # the table takes the height its rows take, capped by the screen
        needed = (self.right.horizontalHeader().sizeHint().height()
                  + sum(self.right.rowHeight(r) for r in range(len(keys)))
                  + self.right.horizontalScrollBar().sizeHint().height()
                  + 2 * self.right.frameWidth() + 4)
        screen = QtWidgets.QApplication.primaryScreen()
        cap = int(screen.availableGeometry().height() * 0.45) if screen \
            else 500
        self.setFixedHeight(max(120, min(needed, cap)))

        cur = current_scope()
        if cur in self.workbenches:
            col = self.workbenches.index(cur)
            hdr = self.right.horizontalHeaderItem(col)
            if hdr is not None:
                font = hdr.font()
                font.setBold(True)
                hdr.setFont(font)
                hdr.setToolTip("current workbench")
            tint = self.palette().highlight().color()
            tint.setAlpha(45)
            for row in range(self.right.rowCount()):
                item = self.right.item(row, col)
                if item is not None:
                    item.setBackground(QtGui.QBrush(tint))
            if self.right.rowCount():
                self.right.scrollTo(
                    self.right.model().index(0, col),
                    QtWidgets.QAbstractItemView.EnsureVisible)

    def _cell(self, key, scope):
        # the item carries the reference and the tint; the label the text
        item = QtWidgets.QTableWidgetItem()
        item.setData(QtCore.Qt.UserRole, (key, scope))
        return item

    def _cell_label(self, key, scope):
        """One line per gesture the key uses anywhere: '· pie' solid when
        bound here, '↳ pie' dim italic when it flows in from a parent
        scope, '—' when that gesture does nothing in this workbench."""
        lines, tips = [], []
        parents = [s for s in model.scope_chain(scope) if s != scope]
        for g in model.key_gestures(key, self.binds):
            own = self.binds.get(scope, {}).get(key, {}).get(g)
            glyph = f'<span style="color:#888">{GLYPH[g]}</span>'
            inherited = None
            if not own and scope != ANY_SCOPE:
                for parent in parents:
                    got = self.binds.get(parent, {}).get(key, {}).get(g)
                    if got:
                        inherited = (got, parent)
                        break
            if own:
                lines.append(f"{glyph} {own}")
                tips.append(f"{GNAME[g]}: {own}")
            elif inherited:
                got, parent = inherited
                lines.append(f'{glyph} <i style="color:#888">↳ {got}</i>')
                tips.append(f"{GNAME[g]}: {got} — flows in from {parent}")
            else:
                lines.append(f'{glyph} <span style="color:#777">—</span>')
        label = QtWidgets.QLabel("<br>".join(lines))
        label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        label.setContentsMargins(4, 1, 4, 1)
        label.setToolTip("\n".join(tips) or "unbound here")
        return label

    # -- interactions

    def _cell_ref(self, table, row, col):
        item = table.item(row, col)
        return item.data(QtCore.Qt.UserRole) if item else None

    def _jump(self, table, row, col):
        ref = self._cell_ref(table, row, col)
        if not ref:
            return
        key, scope = ref
        entry = dict(self.binds.get(ANY_SCOPE, {}).get(key, {}))
        entry.update(self.binds.get(scope, {}).get(key, {}))
        hit = entry.get("press") or next(iter(entry.values()), None)
        if hit and hit in self.pies:
            self.jump_to_pie.emit(hit)

    def _bind_cell(self, table, row, col):
        ref = self._cell_ref(table, row, col)
        if not ref:
            return
        key, scope = ref
        own = self.binds.get(scope, {}).get(key, {})
        base = self.binds.get(ANY_SCOPE, {}).get(key, {})
        menu = QtWidgets.QMenu(self)
        targets = sorted(self.pies) + [model.SMART_NAME]
        for g in model.GESTURES:
            verb = "Rebind" if g in own else "Bind"
            sub = menu.addMenu(f"{GLYPH[g]}  {verb} the {GNAME[g]}…")
            for name in targets:
                label = name if name != model.SMART_NAME \
                    else f"{name} (most used)"
                sub.addAction(label, lambda _=False, n=name, g=g:
                              self._set(scope, key, n, g))
        menu.addSeparator()
        for g in model.GESTURES:
            if g in own:
                label = (f"{GLYPH[g]}  Revert the {GNAME[g]} to {ANY_SCOPE}"
                         if scope != ANY_SCOPE and base.get(g)
                         else f"{GLYPH[g]}  Clear the {GNAME[g]}")
                menu.addAction(label, lambda _=False, g=g:
                               self._clear(scope, key, g))
        menu.exec_(QtGui.QCursor.pos())

    def _set(self, scope, key, name, gesture="press"):
        model.set_bind(scope, key, name, gesture)
        self.changed.emit()

    def _clear(self, scope, key, gesture="press"):
        model.clear_bind(scope, key, gesture)
        self.changed.emit()

    def _rekey(self, row):
        old = self.keys()[row]
        new = record_key(self, old)
        if not new or new == old or new in self.keys():
            return
        for scope, keys in self.binds.items():
            for g, name in (keys.get(old) or {}).items():
                model.set_bind(scope, new, name, g)
        model.remove_key(old)
        self.changed.emit()

    def _key_menu(self, point):
        row = self.left.verticalHeader().logicalIndexAt(point)
        if row < 0:
            return
        key = self.keys()[row]
        menu = QtWidgets.QMenu(self)
        menu.addAction("Record a different key…", lambda: self._rekey(row))
        menu.addSeparator()
        menu.addAction(f"Remove key {key} — every workbench",
                       lambda: (model.remove_key(key), self.changed.emit()))
        menu.exec_(QtGui.QCursor.pos())

    def add_key(self):
        new = record_key(self, "")
        if not new or new in self.keys():
            return
        menu = QtWidgets.QMenu(self)
        for name in sorted(self.pies) + [model.SMART_NAME]:
            menu.addAction(f"{new} opens {name} (Any workbench)",
                           lambda n=name: self._set(ANY_SCOPE, new, n))
        menu.exec_(QtGui.QCursor.pos())


class _MouseCatch(QtCore.QObject):
    """While the recorder is up, a spare mouse button is an answer too."""

    def __init__(self, dlg, caught):
        super().__init__(dlg)
        self._dlg = dlg
        self._caught = caught

    def eventFilter(self, _obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            name = runtime.MOUSE_KEYS.get(event.button())
            if name is not None:
                self._caught["key"] = name
                self._dlg.accept()
                return True
        return False


def record_key(parent, current):
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Shortcut key")
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        "Press a key (modifiers are included) —\n"
        "or click a spare mouse button (back/forward)."))
    edit = QtWidgets.QKeySequenceEdit()
    if current:
        edit.setKeySequence(QtGui.QKeySequence(current))
    lay.addWidget(edit)
    bb = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    caught = {}
    catcher = _MouseCatch(dlg, caught)
    app = QtWidgets.QApplication.instance()
    app.installEventFilter(catcher)
    try:
        accepted = dlg.exec_() == QtWidgets.QDialog.Accepted
    finally:
        app.removeEventFilter(catcher)
    if not accepted:
        return None
    if caught.get("key"):
        return caught["key"]
    seq = edit.keySequence().toString()
    return seq.split(",")[0].strip() if seq else None


# ---- behaviour -------------------------------------------------------------

# ---- the main dialog -------------------------------------------------------

class SliderSpin(QtWidgets.QWidget):
    changed = QtCore.Signal(int)

    def __init__(self, value, lo, hi, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setValue(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)

    def _from_slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.changed.emit(v)

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.changed.emit(v)


class PieMenuPreferences(QtWidgets.QDialog):
    def __init__(self, parent=None, on_change=None, workbenches=None):
        super().__init__(parent)
        self.setWindowTitle("PieMenu preferences")
        self.on_change = on_change or (lambda: None)
        self.actions = list_commands()
        self.pies = model.load_pies()
        if not self.pies:
            pie = Pie("Main")
            model.normalise(pie)
            model.save_pie(pie)
            self.pies = model.load_pies()
        if model.SMART_NAME not in self.pies:
            # the Smart pie's layout and behaviour are editable like any
            # other; only its contents are computed
            smart = Pie(model.SMART_NAME, slots=8, per_ring=8)
            model.save_pie(smart)
            self.pies[model.SMART_NAME] = smart
        self.binds = model.load_binds()
        self.current = min(self.pies)
        self.slot = 0
        self.binding = 0
        self._trimmed = {}    # pie -> {slot index: bindings cut by a shrink}
        # the whole tree as it was when this window opened, for Revert
        self._session_snapshot = os.path.join(
            tempfile.gettempdir(), f"piemenu-session-{os.getpid()}.FCParam")
        try:
            App.ParamGet("User parameter:BaseApp/PieMenu").Export(
                self._session_snapshot)
        except Exception:  # noqa: BLE001 -- no Export on odd builds
            self._session_snapshot = None

        outer = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        outer.addLayout(top, 1)

        # -- pies list
        left_frame, left = _panel()
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Pies"))
        bar.addStretch(1)
        add_btn = QtWidgets.QToolButton()
        add_btn.setText("+")
        add_menu = QtWidgets.QMenu(add_btn)
        add_menu.addAction("Empty pie…", self.pie_add)
        add_menu.addAction("From a toolbar…", self.pie_from_toolbar)
        tsub = add_menu.addMenu("From a template")
        for tname in TEMPLATES:
            tsub.addAction(tname,
                           lambda t=tname: self.pie_from_template(t))
        preset_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "presets")
        presets = sorted(f for f in os.listdir(preset_dir)
                         if f.endswith(".piemenu.json")) \
            if os.path.isdir(preset_dir) else []
        if presets:
            psub = add_menu.addMenu("From a preset")
            for fname in presets:
                full = os.path.join(preset_dir, fname)
                psub.addAction(
                    fname[:-len(".piemenu.json")],
                    lambda _=False, p=full: self.pie_import_file(p))
        add_menu.addAction("Browse community presets…",
                           lambda: browse_presets_dialog(
                               self, self.pie_import_file).exec_())
        add_menu.addAction("Import…", self.pie_import)
        add_btn.setMenu(add_menu)
        add_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        bar.addWidget(add_btn)
        left.addLayout(bar)
        self.pie_filter = QtWidgets.QLineEdit()
        self.pie_filter.setPlaceholderText("Filter…")
        self.pie_filter.setClearButtonEnabled(True)
        self.pie_filter.textChanged.connect(self._filter_pies)
        left.addWidget(self.pie_filter)
        self.pie_list = QtWidgets.QListWidget()
        self.pie_list.setFixedWidth(200)
        self.pie_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self.pie_list.setTextElideMode(QtCore.Qt.ElideRight)
        self.pie_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        delete_sc = QtGui.QShortcut(QtGui.QKeySequence.Delete, self.pie_list)
        delete_sc.setContext(QtCore.Qt.WidgetShortcut)
        delete_sc.activated.connect(self.pie_delete)
        self.pie_list.currentTextChanged.connect(self._pie_picked)
        self.pie_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.pie_list.customContextMenuRequested.connect(self._pie_menu)
        left.addWidget(self.pie_list, 1)
        top.addWidget(left_frame)

        # -- preview
        self.preview = PreviewWidget()
        self.preview.slot_selected.connect(self._slot_picked)
        self.preview.slot_activated.connect(lambda i: self.add_tool(i))
        self.preview.slots_swapped.connect(self._swap)
        self.preview.slot_menu.connect(self._slot_context)
        pv_frame, pv_lay = _panel()
        pv_head = QtWidgets.QHBoxLayout()
        pv_head.addStretch(1)
        pv_head.addWidget(_help_button(
            "n badge — several tools share the slot<br>"
            "dot — conditional<br>ring — opens another pie<br>"
            "dashed — empty<br>red — context clash"))
        pv_lay.addLayout(pv_head)
        pv_lay.addWidget(self.preview)
        top.addWidget(pv_frame, 1)

        # -- slots table
        mid_frame, mid = _panel()
        mid_bar = QtWidgets.QHBoxLayout()
        self.slots_label = QtWidgets.QLabel("Slots")
        mid_bar.addWidget(self.slots_label)
        mid_bar.addStretch(1)
        add_btn = QtWidgets.QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("Add a tool to the selected slot")
        add_btn.clicked.connect(lambda: self.add_tool(self.slot))
        mid_bar.addWidget(add_btn)
        mid.addLayout(mid_bar)
        self.slots = QtWidgets.QTreeWidget()
        self.slots.setColumnCount(2)
        self.slots.setHeaderLabels(["Tool", "When"])
        self.slots.setFixedWidth(380)
        self.slots.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self.slots.setTextElideMode(QtCore.Qt.ElideRight)
        self.slots.header().setStretchLastSection(True)
        self.slots.setMouseTracking(True)
        self.slots.itemClicked.connect(self._slot_row_clicked)
        self.slots.itemEntered.connect(self._slot_row_hover)
        self.slots.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.slots.customContextMenuRequested.connect(self._binding_menu)
        mid.addWidget(self.slots, 1)
        top.addWidget(mid_frame)

        # -- settings
        self.settings_area = QtWidgets.QScrollArea()
        self.settings_area.setWidgetResizable(True)
        self.settings_area.setFixedWidth(360)
        self.settings_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self.settings_area.setStyleSheet(
            "QScrollArea{background:transparent;"
            "border:1px solid palette(mid);border-radius:4px}"
            "QScrollArea>QWidget>QWidget{background:transparent}")
        top.addWidget(self.settings_area)

        # -- shortcuts
        sc_frame, sc_lay = _panel()
        sc_head = QtWidgets.QHBoxLayout()
        sc_head.addWidget(QtWidgets.QLabel("Shortcuts"))
        sc_head.addStretch(1)
        sc_head.addWidget(_help_button(
            "· press &nbsp; ·· double-press &nbsp; — press-and-hold &nbsp; "
            "··— double-press-and-hold — four pies per key; whether release "
            "fires (gesture pies) or the pie stays for clicking is its "
            "'Run on'<br>an ambiguous press (hold pie waiting out a "
            "possible double) opens the moment the mouse moves — motion "
            "means gesturing, and it counts toward the aim<br>"
            "↳ italic flows in from Any workbench<br>"
            "the bold tinted column is the current workbench<br>"
            "double-click binds the press, right-click everything else"))
        sc_lay.addLayout(sc_head)
        self.shortcuts = ShortcutsTable(workbenches=workbenches)
        self.shortcuts.changed.connect(self._binds_changed)
        self.shortcuts.jump_to_pie.connect(self.select_pie)
        sc_lay.addWidget(self.shortcuts)
        outer.addWidget(sc_frame)

        # the global surface, inlined: the accent override and backup
        foot = QtWidgets.QHBoxLayout()
        add_key = QtWidgets.QPushButton("Add a shortcut key…")
        add_key.clicked.connect(self.shortcuts.add_key)
        foot.addWidget(add_key)
        foot.addSpacing(16)
        colors_btn = QtWidgets.QPushButton("Colors…")
        colors_btn.setToolTip("Accent, outline, fill and arrow colors — "
                               "each follows the FreeCAD theme unless "
                               "overridden.")
        colors_btn.clicked.connect(
            lambda: colors_dialog(self, self.on_change).exec_())
        foot.addWidget(colors_btn)
        stats_btn = QtWidgets.QPushButton("Stats…")
        stats_btn.setToolTip("Your most used tools, and the reset.")
        stats_btn.clicked.connect(lambda: stats_dialog(self).exec_())
        foot.addWidget(stats_btn)
        keys_btn = QtWidgets.QPushButton("Keys…")
        keys_btn.setToolTip("Everything the keyboard does, on one page.")
        keys_btn.clicked.connect(lambda: keys_dialog(self).exec_())
        foot.addWidget(keys_btn)
        p = App.ParamGet(runtime.MAIN)
        auto = QtWidgets.QCheckBox("Auto-open on selection")
        auto.setChecked(p.GetBool("AutoOpenSelection", False))
        auto.toggled.connect(lambda v: p.SetBool("AutoOpenSelection", v))
        auto.setToolTip("When the selection changes and the workbench's pie "
                        "has a matching conditional slot, open it at the "
                        "cursor unasked.")
        foot.addWidget(auto)
        foot.addStretch(1)

        root = App.ParamGet("User parameter:BaseApp/PieMenu")

        def export_all():
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export all PieMenu settings", "piemenu.FCParam")
            if path:
                root.Export(path)

        def import_all():
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Import PieMenu settings")
            if path:
                root.Import(path)
                self._binds_changed()

        def revert_session():
            if self._session_snapshot is None \
                    or not os.path.exists(self._session_snapshot):
                return
            answer = QtWidgets.QMessageBox.question(
                self, "Revert",
                "Put everything back the way it was when this window "
                "opened?")
            if answer != QtWidgets.QMessageBox.Yes:
                return
            root.Import(self._session_snapshot)
            self.pies = model.load_pies()
            self.current = self.current if self.current in self.pies \
                else min(self.pies)
            self._binds_changed()

        for label, fn in (("Export…", export_all), ("Import…", import_all),
                          ("Revert…", revert_session)):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(fn)
            if not hasattr(root, "Export"):
                btn.setEnabled(False)
            if label.startswith("Revert"):
                btn.setToolTip("Back to how everything was when this "
                               "window opened.")
            foot.addWidget(btn)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        outer.addLayout(foot)

        self.refresh()

    # -- data plumbing

    def pie(self):
        return self.pies[self.current]

    def _changed(self, structure=False):
        model.save_pie(self.pie())
        self.binds = model.load_binds()
        self.on_change()
        if structure:
            self._queue_refresh()
        else:
            self.preview.set_pie(self.pie(), self.actions)
            self._fill_settings_labels()

    def _binds_changed(self):
        self.binds = model.load_binds()
        self.on_change()
        self._queue_refresh()

    def _queue_refresh(self):
        """refresh() next tick, never now: the sender (the family combo with
        its dropdown still delivering, a shortcut cell) is destroyed by the
        rebuild, and tearing it down mid-signal is a use-after-free."""
        if not getattr(self, "_refresh_queued", False):
            self._refresh_queued = True
            QtCore.QTimer.singleShot(0, self._run_refresh)

    def _run_refresh(self):
        self._refresh_queued = False
        self.refresh()

    def refresh(self):
        pies, binds = self.pies, self.binds
        self.pie_list.blockSignals(True)
        self.pie_list.clear()
        reached = set()
        for scope in binds.values():
            for gestures in scope.values():
                reached.update(gestures.values())
        for name in sorted(pies):
            filled = sum(1 for s in pies[name].items if s)
            label = f"{name} · {filled}"
            if pies[name].default:
                label += "   (default)"
            elif name not in reached and not doors_into(pies, name):
                label += "   (unused)"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, name)
            item.setIcon(runtime.pie_icon(pies[name]))
            self.pie_list.addItem(item)
            if name == self.current:
                self.pie_list.setCurrentItem(item)
        self.pie_list.blockSignals(False)
        self._filter_pies(self.pie_filter.text())

        pie = self.pie()
        model.normalise(pie)
        if pie.name == model.SMART_NAME:
            # show what Smart would serve right now; edits to slots are
            # pointless (they are recomputed at every open)
            model.fill_smart(pie, current_scope() or model.ANY_SCOPE)
        self.slot = min(self.slot, model.slot_count(pie) - 1)
        self.preview.set_pie(pie, self.actions)
        self.preview.set_selected(self.slot)
        self._fill_slots()
        self._fill_settings()
        self.shortcuts.rebuild(pies, binds)

    # -- pies list

    def select_pie(self, name):
        if name in self.pies:
            self.current = name
            self.slot = 0
            self.refresh()

    def _filter_pies(self, text):
        needle = text.strip().lower()
        for i in range(self.pie_list.count()):
            item = self.pie_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _pie_picked(self, _label):
        item = self.pie_list.currentItem()
        if item is not None:
            self.current = item.data(QtCore.Qt.UserRole)
            self.slot = 0
            self.refresh()

    def _pie_menu(self, point):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Rename…", self.pie_rename)
        menu.addAction("Duplicate", self.pie_duplicate)
        selected = [n for n in self._selected_pie_names()
                    if n != model.SMART_NAME]
        label = f"Delete {len(selected)} pies" if len(selected) > 1 \
            else "Delete"
        act = menu.addAction(label, self.pie_delete)
        act.setEnabled(len(self.pies) > 1 and bool(selected))
        menu.addSeparator()
        menu.addAction("Use when no workbench matches", self.pie_default)
        pin = menu.addAction("Pin to screen", self._pin_current)
        pin.setEnabled(runtime.runtime is not None)
        menu.addSeparator()
        menu.addAction("Export this pie…", self.pie_export)
        menu.addAction("Import a pie…", self.pie_import)
        menu.addAction("New from a toolbar…", self.pie_from_toolbar)
        menu.exec_(self.pie_list.mapToGlobal(point))

    def _pin_current(self):
        if runtime.runtime is not None:
            runtime.runtime.pin_pie(self.current)

    def pie_export(self):
        pie = self.pie()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export pie", f"{pie.name}.piemenu.json",
            "PieMenu pies (*.piemenu.json)")
        if not path:
            return
        data = {f: getattr(pie, f) for f in
                ("name", "family", "icon", "slots", "per_ring", "ring_mode",
                 "ring_counts", "radius", "arc", "arc_face", "stagger",
                 "stagger_by", "cols", "rows", "anchors", "anchor_offsets",
                 "button", "spacing", "accent", "run_on", "delay",
                 "show_names", "alt_size", "door_hover")}
        data["items"] = [[{"cmd": b.cmd, "rule": model.encode_rule(b.rule),
                           "label": b.label}
                          for b in (slot or [])] for slot in pie.items]
        data["requires"] = model.pie_requires(pie)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)

    def pie_import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import a pie", "", "PieMenu pies (*.piemenu.json)")
        if path:
            self.pie_import_file(path)

    def pie_import_file(self, path, confirm=True, source=""):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            missing = missing_requirements(data)
            if confirm and missing:
                answer = QtWidgets.QMessageBox.question(
                    self, "Missing workbenches",
                    "This pie uses tools that are not installed here:\n"
                    + ", ".join(missing) + "\n\nThose slots will show as "
                    "unavailable until you install them (Addon Manager). "
                    "Import anyway?")
                if answer != QtWidgets.QMessageBox.Yes:
                    return
            items = data.pop("items", [])
            pie = Pie(name="Imported")
            for key, value in data.items():
                if hasattr(pie, key):
                    setattr(pie, key, value)
            # a preset installed from the same place again updates in
            # place instead of piling up Name-2, Name-3 copies
            replacing = next((p.name for p in self.pies.values()
                              if source and p.source == source), None)
            pie.name = replacing or self._unique(
                str(data.get("name", "Imported")))
            pie.source = source
            pie.default = False
            model.normalise(pie)
            for i, slot in enumerate(items[:len(pie.items)]):
                bindings = [Binding(e["cmd"],
                                    model.decode_rule(e.get("rule", "")),
                                    e.get("label", ""))
                            for e in slot if e.get("cmd")]
                pie.items[i] = bindings or None
        except Exception as exc:  # noqa: BLE001 -- bad file, tell the user
            if confirm:
                QtWidgets.QMessageBox.warning(self, "Import failed",
                                              str(exc))
            return
        model.save_pie(pie)
        self.pies[pie.name] = pie
        self.select_pie(pie.name)
        self.on_change()

    def pie_from_template(self, tname):
        cmds = TEMPLATES[tname]
        pie = Pie(self._unique(tname), slots=max(4, len(cmds)), per_ring=8)
        model.normalise(pie)
        for i, cmd in enumerate(cmds):
            pie.items[i] = [Binding(cmd)]
        model.save_pie(pie)
        self.pies[pie.name] = pie
        self.select_pie(pie.name)
        self.on_change()

    def pie_from_toolbar(self):
        """Seed a new pie from any toolbar of the main window."""
        if App is None or not App.GuiUp:
            return
        import FreeCADGui as Gui
        mw = Gui.getMainWindow()
        bars = {}
        for bar in mw.findChildren(QtWidgets.QToolBar):
            cmds = [a.objectName() for a in bar.actions()
                    if a.objectName() and "_" in a.objectName()]
            if cmds and bar.windowTitle():
                bars[bar.windowTitle()] = cmds
        if not bars:
            return
        name, ok = QtWidgets.QInputDialog.getItem(
            self, "New pie from a toolbar", "Toolbar:",
            sorted(bars), 0, False)
        if not ok or not name:
            return
        cmds = bars[name][:24]
        pie = Pie(self._unique(name), slots=max(4, len(cmds)),
                  per_ring=8)
        model.normalise(pie)
        for i, cmd in enumerate(cmds):
            pie.items[i] = [Binding(cmd)]
        model.save_pie(pie)
        self.pies[pie.name] = pie
        self.select_pie(pie.name)
        self.on_change()

    def _unique(self, base):
        names = set(self.pies)
        if base not in names:
            return base
        n = 2
        while f"{base}-{n}" in names:
            n += 1
        return f"{base}-{n}"

    def pie_add(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New pie", "Name:")
        if not ok or not name.strip():
            return
        pie = Pie(self._unique(name.strip()))
        model.normalise(pie)
        model.save_pie(pie)
        self.pies = model.load_pies()
        self.select_pie(pie.name)
        self.on_change()

    def pie_rename(self):
        old = self.current
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename pie", "Name:", text=old)
        name = name.strip()
        if not ok or not name or name == old:
            return
        name = self._unique(name)
        pie = self.pie()
        pie.name = name
        model.save_pie(pie)
        model.delete_pie(old)
        # every reference follows the rename: doors and binds
        for other in model.load_pies().values():
            dirty = False
            for slot in other.items:
                for b in slot or []:
                    if is_pie_command(b.cmd) and pie_target(b.cmd) == old:
                        b.cmd = model.PIE_PREFIX + name
                        dirty = True
            if dirty:
                model.save_pie(other)
        for scope, keys in model.load_binds().items():
            for key, target in keys.items():
                if target == old:
                    model.set_bind(scope, key, name)
        self.pies = model.load_pies()
        self.binds = model.load_binds()
        self.current = name
        self.on_change()
        self.refresh()

    def pie_duplicate(self):
        import copy
        pie = copy.deepcopy(self.pie())
        pie.name = self._unique(pie.name)
        pie.default = False
        model.save_pie(pie)
        self.pies = model.load_pies()
        self.select_pie(pie.name)
        self.on_change()

    def _selected_pie_names(self):
        names = [item.data(QtCore.Qt.UserRole)
                 for item in self.pie_list.selectedItems()]
        return [n for n in names if n] or [self.current]

    def pie_delete(self):
        self.pies_delete(self._selected_pie_names())

    def pies_delete(self, names, confirm=True):
        names = [n for n in names
                 if n in self.pies and n != model.SMART_NAME]
        names = names[:max(0, len(self.pies) - 1)]   # always keep one pie
        if not names:
            return
        if confirm and len(names) > 1:
            answer = QtWidgets.QMessageBox.question(
                self, "Delete pies",
                f"Delete {len(names)} pies?\n" + ", ".join(sorted(names)))
            if answer != QtWidgets.QMessageBox.Yes:
                return
        for name in names:
            model.delete_pie(name)
        self.pies = model.load_pies()
        self.current = self.current if self.current in self.pies \
            else min(self.pies)
        self.binds = model.load_binds()
        self.on_change()
        self.refresh()

    def pie_default(self):
        for name, pie in self.pies.items():
            was = pie.default
            pie.default = name == self.current
            if pie.default != was:
                model.save_pie(pie)
        self.on_change()
        self.refresh()

    # -- slots

    def _fill_slots(self):
        pie = self.pie()
        auto = "  — auto: your most used" \
            if pie.name == model.SMART_NAME else ""
        self.slots_label.setText(
            f"Slots — {pie.name}  "
            f"{sum(1 for s in pie.items if s)}/{model.slot_count(pie)}"
            f"{auto}")
        self.slots.clear()
        # a subtle self-derived tint: alternateBase varies wildly per theme
        tint_c = self.palette().color(QtGui.QPalette.Text)
        tint_c.setAlpha(16)
        tint = QtGui.QBrush(tint_c)
        warn = QtGui.QBrush(QtGui.QColor(200, 70, 60))
        for i, slot in enumerate(pie.items):
            problems = dict(model.slot_check(slot))
            label = f"Slot {i + 1}"
            if slot and len(slot) > 1:
                label += f"   — {len(slot)} tools, first match wins"
            elif not slot:
                label += "   — empty"
            if problems:
                label += "   ⚠ context clash"
            top = QtWidgets.QTreeWidgetItem([label, ""])
            top.setData(0, QtCore.Qt.UserRole, (i, None))
            if problems:
                top.setForeground(0, warn)
                top.setToolTip(0, "\n".join(problems.values()))
            self.slots.addTopLevelItem(top)
            rows = [top]
            for j, b in enumerate(slot or []):
                child = QtWidgets.QTreeWidgetItem(
                    [b.label or command_label(b.cmd), rule_text(b.rule)])
                child.setIcon(0, runtime.pie_icon(
                    self.pies.get(pie_target(b.cmd)))
                    if is_pie_command(b.cmd)
                    else command_icon(b.cmd, self.actions))
                child.setData(0, QtCore.Qt.UserRole, (i, j))
                child.setForeground(1, QtGui.QBrush(QtGui.QColor(128, 128,
                                                                 128)))
                if j in problems:
                    child.setForeground(0, warn)
                    child.setForeground(1, warn)
                    child.setText(1, "always  ⚠")
                    child.setToolTip(0, problems[j])
                    child.setToolTip(1, problems[j])
                top.addChild(child)
                rows.append(child)
            if i % 2:                    # alternate whole slot groups
                for item in rows:
                    item.setBackground(0, tint)
                    item.setBackground(1, tint)
            top.setExpanded(True)
        self.slots.setColumnWidth(0, 210)

    def _slot_picked(self, index):
        self.slot = index
        self.preview.set_selected(index)
        self._fill_slots()

    def _slot_row_clicked(self, item, col):
        ref = item.data(0, QtCore.Qt.UserRole)
        if not ref:
            return
        i, j = ref
        self.slot = i
        self.preview.set_selected(i)
        if j is not None:
            self.binding = j
            if col == 1:
                binding = self.pie().items[i][j]
                edit_rule(self, binding, lambda: self._changed(True))

    def _slot_row_hover(self, item, _col):
        ref = item.data(0, QtCore.Qt.UserRole)
        self.preview.set_highlight(ref[0] if ref else -1)

    def _binding_menu(self, point):
        item = self.slots.itemAt(point)
        if item is None:
            return
        i, j = item.data(0, QtCore.Qt.UserRole)
        pie = self.pie()
        menu = QtWidgets.QMenu(self)
        if j is None:
            menu.addAction("Add a tool…", lambda: self.add_tool(i))
            if pie.items[i]:
                menu.addAction("Clear this slot",
                               lambda: self._clear_slot(i))
        else:
            slot = pie.items[i]
            menu.addAction("Replace tool…",
                           lambda: self.add_tool(i, replace=j))
            menu.addAction("Add another tool…", lambda: self.add_tool(i))
            menu.addAction("Edit rule…",
                           lambda: edit_rule(self, slot[j],
                                             lambda: self._changed(True)))
            menu.addAction("Rename label…",
                           lambda: self._rename_label(i, j))
            menu.addSeparator()
            up = menu.addAction("Move up", lambda: self._move_binding(i, j, -1))
            up.setEnabled(j > 0)
            down = menu.addAction("Move down",
                                  lambda: self._move_binding(i, j, 1))
            down.setEnabled(j < len(slot) - 1)
            menu.addSeparator()
            menu.addAction("Remove", lambda: self._remove_binding(i, j))
        menu.exec_(self.slots.mapToGlobal(point))

    def _slot_context(self, index, global_pos):
        pie = self.pie()
        menu = QtWidgets.QMenu(self)
        menu.addAction("Add a tool…", lambda: self.add_tool(index))
        if pie.items[index]:
            menu.addAction("Clear this slot",
                           lambda: self._clear_slot(index))
        menu.exec_(global_pos)

    def add_tool(self, index, replace=None):
        pie = self.pie()
        slot = pie.items[index] if index < len(pie.items) else None
        binding = slot[replace] if (replace is not None and slot) else None
        dlg = PickerDialog(self.pies, pie, slot, replace_binding=binding,
                           actions=self.actions, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        result = dlg.result_binding()
        if result is None:
            return
        if slot is None:
            pie.items[index] = [result]
        elif replace is not None:
            slot[replace] = result
        else:
            slot.append(result)
        self.slot = index
        self._changed(True)

    def _clear_slot(self, index):
        self.pie().items[index] = None
        self._changed(True)

    def _remove_binding(self, i, j):
        slot = self.pie().items[i]
        del slot[j]
        if not slot:
            self.pie().items[i] = None
        self._changed(True)

    def _move_binding(self, i, j, delta):
        slot = self.pie().items[i]
        slot[j], slot[j + delta] = slot[j + delta], slot[j]
        self._changed(True)

    def _rename_label(self, i, j):
        binding = self.pie().items[i][j]
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Slot label", "Shown instead of the command name:",
            text=binding.label)
        if ok:
            binding.label = text.strip()
            self._changed(True)

    def _swap(self, i, j):
        items = self.pie().items
        items[i], items[j] = items[j], items[i]
        self.slot = j
        self._changed(True)

    # -- settings

    def _fill_settings(self):
        pie = self.pie()
        body = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(body)

        def row(label, widget):
            lab = QtWidgets.QLabel(label + ":")
            tip = HELP.get(label) or HELP.get(label.split()[0], "")
            image = _tip_image(label)
            if image:
                tip = f"<img src='{image}'><br>{tip}"
            if tip:
                # the dotted underline says "hover me, there is help here"
                lab.setStyleSheet(
                    "border-bottom: 1px dotted palette(mid);")
                lab.setToolTip(tip)
                widget.setToolTip(tip)
            form.addRow(lab, widget)
            return widget

        family = row("Family", QtWidgets.QComboBox())
        family.addItems(["circle", "grid"])
        family.setCurrentText(pie.family)
        family.currentTextChanged.connect(self._set_family)

        if pie.family == "circle":
            slots = row("Slots", QtWidgets.QSpinBox())
            slots.setRange(1, 48)
            slots.setValue(pie.slots)
            slots.valueChanged.connect(
                lambda v: self._set("slots", v, structure=True))
            mode = row("Rings", QtWidgets.QComboBox())
            mode.addItems(["uniform", "auto", "custom"])
            mode.setCurrentText(pie.ring_mode)
            mode.currentTextChanged.connect(
                lambda v: self._set("ring_mode", v, structure=True))
            plan = model.ring_plan(pie)
            if pie.ring_mode == "uniform":
                per = QtWidgets.QWidget()
                per_lay = QtWidgets.QHBoxLayout(per)
                per_lay.setContentsMargins(0, 0, 0, 0)
                per_spin = QtWidgets.QSpinBox()
                per_spin.setRange(1, 48)
                per_spin.setValue(pie.per_ring)
                per_spin.valueChanged.connect(
                    lambda v: self._set("per_ring", v, structure=True))
                per_lay.addWidget(per_spin)
                per_lay.addWidget(QtWidgets.QLabel(
                    f"→ {len(plan)} ring{'s' if len(plan) > 1 else ''}"))
                row("Per ring", per)
            elif pie.ring_mode == "auto":
                # each ring takes what its circumference fits; the label
                # follows the arc/radius/spacing sliders live
                self._auto_plan_label = QtWidgets.QLabel(
                    " · ".join(str(c) for c in plan) + "  (by radius)")
                row("Per ring", self._auto_plan_label)
            else:
                ring_edit = QtWidgets.QLineEdit(
                    ",".join(str(c) for c in pie.ring_counts))
                ring_edit.setPlaceholderText("e.g. 8,16 — last repeats")

                def ring_counts_done(edit=ring_edit):
                    values = []
                    for part in edit.text().replace(" ", "").split(","):
                        if part.isdigit() and int(part) > 0:
                            values.append(int(part))
                        elif part:
                            return           # garbage: change nothing
                    self._set("ring_counts", values, structure=True)

                ring_edit.editingFinished.connect(ring_counts_done)
                row("Per ring", ring_edit)
            if pie.ring_mode != "auto":
                self._auto_plan_label = None
            spacing = row("Spacing",
                          self._slider(pie.spacing, 0, 60, "spacing"))
            if len(model.ring_plan(pie)) <= 1:
                # nothing to space: one ring's slots sit on the radius
                spacing.setEnabled(False)
                spacing.setToolTip(
                    "Spacing separates rings — this pie has a single ring, "
                    "so there is nothing to space. Radius moves its slots.")
            row("Radius", self._slider(pie.radius, 20, 300, "radius"))
            row("Arc", self._slider(pie.arc, 10, 360, "arc"))
            row("Facing", self._slider(pie.arc_face, -180, 180, "arc_face"))
            stagger = row("Stagger", QtWidgets.QCheckBox("alternate radius"))
            stagger.setChecked(pie.stagger)
            stagger.toggled.connect(
                lambda v: self._set("stagger", v, structure=True))
            if pie.stagger:
                row("Stagger by",
                    self._slider(pie.stagger_by, -40, 60, "stagger_by"))
        else:
            cols = row("Columns", QtWidgets.QSpinBox())
            cols.setRange(1, 12)
            cols.setValue(pie.cols)
            cols.valueChanged.connect(
                lambda v: self._set("cols", v, structure=True))
            rows_w = row("Rows", QtWidgets.QSpinBox())
            rows_w.setRange(1, 12)
            rows_w.setValue(pie.rows)
            rows_w.valueChanged.connect(
                lambda v: self._set("rows", v, structure=True))
            row("Anchors", self._anchor_cross(pie))
            # one offset per block, so grids can be spaced independently
            for a in [x for x in model.ANCHOR_ORDER
                      if x in pie.anchors and x != "Center"]:
                w = SliderSpin(pie.anchor_offsets.get(a, pie.radius), 0, 300)
                w.changed.connect(
                    lambda v, a=a: self._set_anchor_offset(a, v))
                row(f"Offset {a}", w)
        row("Button", self._slider(pie.button, 16, 96, "button"))
        shape = row("Shape", QtWidgets.QComboBox())
        shape.addItems(["rounded", "square", "squircle", "circle"])
        shape.setCurrentText(pie.shape)
        shape.currentTextChanged.connect(lambda v: self._set("shape", v))
        style = row("Style", QtWidgets.QComboBox())
        style.addItems(["flat", "gradient", "outline"])
        style.setCurrentText(pie.style)
        style.currentTextChanged.connect(lambda v: self._set("style", v))
        if pie.family == "grid":
            row("Spacing", self._slider(pie.spacing, 0, 60, "spacing"))
        row("Chooser size", self._slider(pie.alt_size, 16, 64, "alt_size"))
        accent_box = QtWidgets.QWidget()
        accent_lay = QtWidgets.QHBoxLayout(accent_box)
        accent_lay.setContentsMargins(0, 0, 0, 0)
        accent_pick = QtWidgets.QPushButton("theme" if not pie.accent else "")
        if pie.accent:
            accent_pick.setStyleSheet(f"background:{pie.accent};"
                                      "min-width:60px;")

        def pick_pie_accent(_=False):
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(pie.accent) if pie.accent else runtime.accent(),
                self, "Pie accent")
            if color.isValid():
                self._set("accent", color.name())
                accent_pick.setText("")
                accent_pick.setStyleSheet(f"background:{color.name()};"
                                          "min-width:60px;")

        accent_pick.clicked.connect(pick_pie_accent)
        accent_clear = QtWidgets.QToolButton()
        accent_clear.setText("✕")
        accent_clear.setToolTip("Back to the global accent")
        accent_clear.clicked.connect(
            lambda: (self._set("accent", ""),
                     accent_pick.setText("theme"),
                     accent_pick.setStyleSheet("")))
        accent_lay.addWidget(accent_pick)
        accent_lay.addWidget(accent_clear)
        accent_lay.addStretch(1)
        row("Accent", accent_box)

        run_on = row("Run on", QtWidgets.QComboBox())
        run_on.addItems(["click", "hover", "release"])
        run_on.setCurrentText(pie.run_on)
        run_on.currentTextChanged.connect(lambda v: self._set("run_on", v))
        delay = row("Delay", QtWidgets.QSpinBox())
        delay.setRange(0, 2000)
        delay.setValue(pie.delay)
        delay.valueChanged.connect(lambda v: self._set("delay", v))
        doors = row("Doors on hover",
                    QtWidgets.QCheckBox("after the delay"))
        doors.setChecked(pie.door_hover)
        doors.toggled.connect(lambda v: self._set("door_hover", v))
        names = row("Command names", QtWidgets.QCheckBox("show in slots"))
        names.setChecked(pie.show_names)
        names.toggled.connect(lambda v: self._set("show_names", v))

        opened = QtWidgets.QGroupBox("Opened by")
        ob = QtWidgets.QVBoxLayout(opened)
        ways = [(key, g, scope) for scope, keys in self.binds.items()
                for key, gs in keys.items()
                for g, target in gs.items() if target == pie.name]
        for key, g, scope in sorted(ways):
            where = "in every workbench" if scope == ANY_SCOPE \
                else f"in {scope}"
            ob.addWidget(QtWidgets.QLabel(
                f"key {key} ({GNAME[g]}): {where}"))
        for from_name, slot_i, rule in doors_into(self.pies, pie.name):
            link = QtWidgets.QPushButton(
                f"from {from_name} — slot {slot_i + 1}"
                + (f", {rule_text(rule)}" if rule else ""))
            link.setFlat(True)
            link.setStyleSheet("text-align: left; color: palette(link);")
            link.clicked.connect(
                lambda _=False, n=from_name: self.select_pie(n))
            ob.addWidget(link)
        if not ways and not doors_into(self.pies, pie.name):
            ob.addWidget(QtWidgets.QLabel(
                "Nothing reaches this pie — no shortcut, no door."))
        form.addRow(opened)

        self.settings_area.setWidget(body)

    def _fill_settings_labels(self):
        # the auto ring plan depends on arc/radius/spacing sliders: keep its
        # readout live without rebuilding the panel mid-drag
        label = getattr(self, "_auto_plan_label", None)
        if label is not None and self.pie().ring_mode == "auto":
            plan = model.ring_plan(self.pie())
            label.setText(" · ".join(str(c) for c in plan) + "  (by radius)")

    def _slider(self, value, lo, hi, field):
        w = SliderSpin(value, lo, hi)
        w.changed.connect(lambda v: self._set(field, v))
        return w

    def _set_anchor_offset(self, anchor, value):
        self.pie().anchor_offsets[anchor] = value
        self._changed(False)

    def _anchor_cross(self, pie):
        grid = QtWidgets.QWidget()
        lay = QtWidgets.QGridLayout(grid)
        lay.setContentsMargins(0, 0, 0, 0)
        cells = {"Top": (0, 1), "Left": (1, 0), "Center": (1, 1),
                 "Right": (1, 2), "Bottom": (2, 1)}
        glyph = {"Top": "▲", "Bottom": "▼", "Left": "◀", "Right": "▶",
                 "Center": "●"}

        def toggle(anchor):
            if anchor in pie.anchors:
                if len(pie.anchors) > 1:
                    pie.anchors.remove(anchor)
            else:
                pie.anchors.append(anchor)
            self._set("anchors", pie.anchors, structure=True)

        for anchor, (r, c) in cells.items():
            btn = QtWidgets.QToolButton()
            btn.setText(glyph[anchor])
            btn.setCheckable(True)
            btn.setChecked(anchor in pie.anchors)
            btn.setToolTip(f"a block {anchor.lower()} of the cursor — toggle;"
                           " several at once is fine")
            btn.clicked.connect(lambda _=False, a=anchor: toggle(a))
            lay.addWidget(btn, r, c)
        blocks = len(pie.anchors)
        lay.addWidget(QtWidgets.QLabel(
            f"→ {blocks} block{'s' if blocks > 1 else ''} · "
            f"{model.slot_count(pie)} slots"), 1, 3)
        return grid

    def _set(self, field, value, structure=False):
        if structure:
            self._structural(lambda p: setattr(p, field, value))
        else:
            setattr(self.pie(), field, value)
            self._changed(False)
            if field == "alt_size":
                # the chooser only exists in live pies: demo it right here
                pie = self.pie()
                index = next((i for i, s in enumerate(pie.items)
                              if s and len(s) > 1), self.slot)
                self.preview.flash_chooser(index, value)

    def _set_family(self, family):
        self._structural(lambda p: setattr(p, "family", family))

    def _structural(self, mutate):
        """A shape change (slots, grid, family, anchors).  Whatever falls
        off the end is stashed for this dialog's lifetime, so mistyping a
        count and typing it back loses nothing."""
        pie = self.pie()
        old_items = list(pie.items)
        mutate(pie)
        model.normalise(pie)
        stash = self._trimmed.setdefault(pie.name, {})
        for i, slot in enumerate(old_items):
            if i >= len(pie.items) and slot:
                stash[i] = slot
        for i in sorted(stash):
            if i < len(pie.items) and not pie.items[i]:
                pie.items[i] = stash.pop(i)
        self._changed(True)


_open_dialog = None


def open_preferences(parent=None, on_change=None):
    """Non-modal: tune with one hand, try the pies with the other."""
    global _open_dialog
    if _open_dialog is not None and _open_dialog.isVisible():
        _open_dialog.raise_()
        _open_dialog.activateWindow()
        return _open_dialog
    dlg = PieMenuPreferences(parent, on_change=on_change)
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        dlg.resize(min(1560, int(avail.width() * 0.85)),
                   min(1000, int(avail.height() * 0.85)))
    else:
        dlg.resize(1560, 1000)
    dlg.show()
    _open_dialog = dlg
    return dlg
