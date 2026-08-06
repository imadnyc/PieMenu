"""The v2 data model: pies, slots, bindings, rules, shortcuts.

What the redesign settled (UI-FEEDBACK.md, mockups/preferences2.html):

- pies are a flat set, and a pie is an ordinary command (``PieMenu_<name>``),
  so a slot can open a pie the same way it runs a tool;
- a slot is an ordered list of (rule -> command) bindings -- first match wins,
  several matches offer the chooser;
- a rule is a sparse six-axis condition: ``{axis: (sign, count)}`` -- the same
  comparison ``matchesContext`` evaluates, without the dense storage;
- shortcuts are workbench-scoped: ``binds[scope][key] = pie name``, where the
  ``Any`` scope is the base a specific workbench overrides.

The pure logic (rules, layout, resolution) has no FreeCAD dependency so plain
python can exercise it; the parameter IO needs FreeCAD and is covered by the
headless tests (``dev/test_model.py`` under freecadcmd).
"""

import math
import re
from dataclasses import dataclass, field

try:
    import FreeCAD as App
except ImportError:  # pure-logic callers (plain python) never touch the IO
    App = None

from . import constants

V2_ROOT = "User parameter:BaseApp/PieMenu/V2"
ANY_SCOPE = "Any"
AXES = ("Vertex", "Edge", "Face", "Object", "Axis", "Plane")
PIE_PREFIX = "PieMenu_"
ANCHOR_ORDER = ("Top", "Left", "Center", "Right", "Bottom")

SCHEMA_VERSION = 2


# ---- rules ----------------------------------------------------------------

_SIGNS = constants.get_signs()
# longest first so "<=" is not read as "<"
_RULE_RX = re.compile(
    rf"^({'|'.join(AXES)})(<=|>=|==|!=|<|>)(\d+)$"
)


def encode_rule(rule):
    """{axis: (sign, count)} -> "Face>=1;Edge>=1".  {} -> "" (always)."""
    parts = []
    for axis in AXES:  # canonical order, so encoding is stable
        if axis in rule:
            sign, value = rule[axis]
            if sign not in _SIGNS:
                raise ValueError(f"bad sign {sign!r}")
            parts.append(f"{axis}{sign}{int(value)}")
    return ";".join(parts)


def decode_rule(text):
    """Inverse of encode_rule.  Raises ValueError on garbage."""
    rule = {}
    for part in filter(None, (text or "").split(";")):
        m = _RULE_RX.match(part.strip())
        if not m:
            raise ValueError(f"bad rule segment {part!r}")
        rule[m.group(1)] = (m.group(2), int(m.group(3)))
    return rule


def match_rule(rule, counts):
    """Does a selection (counts per axis) satisfy a sparse rule?

    An axis the rule does not name is "don't care"; the empty rule is always
    true.  counts is a mapping axis -> int; missing axes count as 0.
    """
    for axis, (sign, value) in (rule or {}).items():
        if not _SIGNS[sign](counts.get(axis, 0), value):
            return False
    return True


# ---- bindings and slots ---------------------------------------------------

@dataclass
class Binding:
    """One (rule -> command) entry of a slot."""
    cmd: str
    rule: dict = field(default_factory=dict)


def is_pie_command(cmd):
    return bool(cmd) and cmd.startswith(PIE_PREFIX)


def pie_target(cmd):
    return cmd[len(PIE_PREFIX):]


def live_bindings(slot, counts):
    """The bindings of one slot that apply to the selection, in order.

    Several mean the chooser; slot_face() picks the one the button wears.
    """
    return [b for b in (slot or []) if match_rule(b.rule, counts)]


def slot_check(slot):
    """Per-slot context lint: [(binding index, message)] for suspect mixes.

    Mixing an always-on binding with conditional ones is flagged: the
    always-on binding matches in every context, so the slot never goes
    dead and the conditions stop gating anything.  A slot that is all
    conditional, or all always-on (a plain overload), is fine.
    """
    slot = slot or []
    always = [i for i, b in enumerate(slot) if not b.rule]
    gated = [i for i, b in enumerate(slot) if b.rule]
    if always and gated:
        msg = ("always available, but this slot also has conditional tools "
               "— the slot never goes dead, and this tool joins every "
               "chooser")
        return [(i, msg) for i in always]
    return []


def slot_face(slot, counts, last=None):
    """The binding an overloaded slot presents -- and fires on plain use:
    the last explicitly chosen one if it still applies, else the first."""
    live = live_bindings(slot, counts)
    if not live:
        return None
    if last:
        for b in live:
            if b.cmd == last:
                return b
    return live[0]


# ---- pies -----------------------------------------------------------------

@dataclass
class Pie:
    name: str
    family: str = "circle"          # "circle" | "grid"
    icon: str = ""
    default: bool = False
    # circle
    slots: int = 8
    per_ring: int = 8
    radius: int = 80
    arc: int = 360
    arc_face: int = -90
    stagger: bool = False
    stagger_by: int = 18
    # grid
    cols: int = 3
    rows: int = 2
    anchors: list = field(default_factory=lambda: ["Center"])
    # shared
    button: int = 34
    spacing: int = 6
    # trigger
    open_on: str = "single"         # single | double | hold | double-hold
    run_on: str = "click"           # click | hover | release
    delay: int = 250
    show_names: bool = False
    alt_size: int = 24              # chooser (overload menu) button size
    door_hover: bool = True         # dwelling on a door descends into it
    # items[i] is a slot: a list of Bindings, or None for an empty slot
    items: list = field(default_factory=list)
    # slot index -> cmd the user last picked from that slot's chooser
    last_used: dict = field(default_factory=dict)
    # grid: anchor -> its own offset from the cursor (falls back to radius),
    # so blocks can be spaced independently and never collide
    anchor_offsets: dict = field(default_factory=dict)


def slot_count(pie):
    if pie.family == "circle":
        return max(1, pie.slots)
    return max(1, pie.cols) * max(1, pie.rows) * max(1, len(pie.anchors))


def normalise(pie):
    """Pad or trim items to slot_count, preserving what fits."""
    n = slot_count(pie)
    while len(pie.items) < n:
        pie.items.append(None)
    del pie.items[n:]
    return pie


def positions(pie):
    """Slot centres relative to the cursor, matching the mockup exactly.

    Circle: rings of per_ring slots; a full arc starts at the facing angle, a
    partial arc is centred on it; stagger pushes alternate slots stagger_by
    further out (negative pulls inward).

    Grid: one cols x rows block per active anchor, blocks filled in the fixed
    ANCHOR_ORDER so slot indices are stable as anchors toggle.
    """
    out = []
    n = slot_count(pie)
    step = pie.button + pie.spacing
    if pie.family == "circle":
        per = max(1, min(pie.per_ring, n))
        span = math.radians(pie.arc)
        face = math.radians(pie.arc_face)
        start = face if pie.arc >= 360 else face - span / 2
        for i in range(n):
            ring, k = divmod(i, per)
            in_ring = min(per, n - ring * per)
            div = in_ring if pie.arc >= 360 else max(1, in_ring - 1)
            a = start + (span / div) * k
            r = pie.radius + ring * (pie.button + pie.spacing + 10)
            if pie.stagger and k % 2:
                r += pie.stagger_by
            out.append((math.cos(a) * r, math.sin(a) * r))
        return out
    cols, rows = max(1, pie.cols), max(1, pie.rows)
    per = cols * rows
    order = [a for a in ANCHOR_ORDER if a in pie.anchors] or ["Center"]
    for i in range(n):
        blk = min(i // per, len(order) - 1)
        k = i % per
        anchor = order[blk]
        x = (k % cols - (cols - 1) / 2) * step
        y = (k // cols - (rows - 1) / 2) * step
        off = pie.anchor_offsets.get(anchor, pie.radius)
        off_y = off / 2 + ((rows - 1) / 2) * step
        off_x = off / 2 + ((cols - 1) / 2) * step
        if anchor == "Top":
            y -= off_y
        elif anchor == "Bottom":
            y += off_y
        elif anchor == "Left":
            x -= off_x
        elif anchor == "Right":
            x += off_x
        out.append((x, y))
    return out


def pie_live(name, pies, counts, _seen=None):
    """Is anything in this pie actually usable under the selection?

    A binding to a command counts when its rule matches; a binding to a pie
    counts when that pie is (recursively) live.  The visited set makes cycles
    terminate -- cycles are legal (View can contain Main).
    """
    pie = pies.get(name)
    if pie is None:
        return False
    seen = _seen or set()
    if name in seen:
        return False
    seen.add(name)
    for slot in pie.items:
        for b in live_bindings(slot, counts):
            if not is_pie_command(b.cmd):
                return True
            if pie_live(pie_target(b.cmd), pies, counts, seen):
                return True
    return False


# ---- shortcuts ------------------------------------------------------------
# A binding is key x scope x GESTURE -> pie. Four gestures: press (a tap),
# double (two taps), hold (press and keep it down), double-hold (tap, then
# press and hold). One key can reach four pies per workbench; each gesture
# inherits through the Any scope independently. What RELEASE means is the
# pie's own run_on: a release pie follows the aim and never outlives the
# key; a click/hover pie stays for the mouse and toggles.

GESTURES = ("press", "double", "hold", "double-hold")

def resolve_key(key, workbench, binds, gesture="press"):
    """(pie name, scope) for a key + gesture in a workbench, or None.

    The whole rule: the workbench's own binding beats the Any scope; if
    neither names the key for that gesture, the gesture does nothing.
    """
    for scope in (workbench, ANY_SCOPE):
        name = binds.get(scope, {}).get(key, {}).get(gesture)
        if name:
            return name, scope
    return None


def gestures_for(key, workbench, binds):
    """{gesture: (pie name, scope)} — every gesture the key answers here."""
    out = {}
    for gesture in GESTURES:
        hit = resolve_key(key, workbench, binds, gesture)
        if hit:
            out[gesture] = hit
    return out


def key_gestures(key, binds):
    """The gestures a key uses in any scope, canonical order, press always."""
    used = {g for scope in binds.values()
            for g in (scope.get(key) or {})}
    used.add("press")
    return [g for g in GESTURES if g in used]


# ---- ParamGet IO ----------------------------------------------------------

def _grp(path=""):
    return App.ParamGet(V2_ROOT + ("/" + path if path else ""))


_BOOLS = ("default", "stagger", "show_names", "door_hover")
_INTS = ("slots", "per_ring", "radius", "arc", "arc_face", "stagger_by",
         "cols", "rows", "button", "spacing", "delay", "alt_size")
_STRINGS = ("family", "icon", "open_on", "run_on")
_PARAM = {f: "".join(w.capitalize() for w in f.split("_")) for f in
          _BOOLS + _INTS + _STRINGS}


def save_pie(pie):
    normalise(pie)
    g = _grp("Pies/" + pie.name)
    for f in _BOOLS:
        g.SetBool(_PARAM[f], getattr(pie, f))
    for f in _INTS:
        g.SetInt(_PARAM[f], int(getattr(pie, f)))
    for f in _STRINGS:
        g.SetString(_PARAM[f], getattr(pie, f))
    g.SetString("Anchors", ",".join(pie.anchors))
    for a in ANCHOR_ORDER:
        if a in pie.anchor_offsets:
            g.SetInt("Offset" + a, int(pie.anchor_offsets[a]))
        else:
            g.RemInt("Offset" + a)
    g.RemGroup("Slots")
    slots = g.GetGroup("Slots")
    for i, slot in enumerate(pie.items):
        if not slot:
            continue
        sg = slots.GetGroup(f"S{i}")
        if pie.last_used.get(i):
            sg.SetString("Last", pie.last_used[i])
        for j, b in enumerate(slot):
            bg = sg.GetGroup(f"B{j}")
            bg.SetString("Command", b.cmd)
            bg.SetString("Rule", encode_rule(b.rule))


def set_last_used(name, index, cmd):
    """Record a chooser pick without rewriting the whole pie."""
    _grp(f"Pies/{name}/Slots").GetGroup(f"S{index}").SetString("Last", cmd)


def load_pie(name):
    g = _grp("Pies/" + name)
    pie = Pie(name=name)
    for f in _BOOLS:
        setattr(pie, f, g.GetBool(_PARAM[f], getattr(pie, f)))
    for f in _INTS:
        setattr(pie, f, g.GetInt(_PARAM[f], getattr(pie, f)))
    for f in _STRINGS:
        setattr(pie, f, g.GetString(_PARAM[f], getattr(pie, f)))
    anchors = [a for a in g.GetString("Anchors", "Center").split(",")
               if a in ANCHOR_ORDER]
    pie.anchors = anchors or ["Center"]
    for a in ANCHOR_ORDER:
        v = g.GetInt("Offset" + a, -1)
        if v >= 0:
            pie.anchor_offsets[a] = v
    normalise(pie)
    slots = g.GetGroup("Slots")
    for sname in slots.GetGroups():
        try:
            i = int(sname[1:])
        except ValueError:
            continue
        if not 0 <= i < len(pie.items):
            continue
        sg = slots.GetGroup(sname)
        last = sg.GetString("Last", "")
        if last:
            pie.last_used[i] = last
        bindings = []
        for bname in sorted(sg.GetGroups(), key=lambda s: int(s[1:])):
            bg = sg.GetGroup(bname)
            cmd = bg.GetString("Command", "")
            if cmd:
                bindings.append(Binding(cmd, decode_rule(bg.GetString("Rule", ""))))
        pie.items[i] = bindings or None
    return pie


def load_pies():
    """name -> Pie for every stored pie."""
    return {name: load_pie(name) for name in _grp("Pies").GetGroups()}


def delete_pie(name):
    _grp("Pies").RemGroup(name)


def _bind_param(key, gesture):
    """Param name for a binding: bare key = press (which is also what every
    pre-gesture config stored), 'KEY gesture' otherwise. Keys never contain
    spaces (QKeySequence writes Ctrl+Shift+P), so the split is safe."""
    return key if gesture == "press" else f"{key} {gesture}"


def load_binds():
    """{scope: {key: {gesture: pie name}}} straight off the parameter tree."""
    binds = {}
    root = _grp("Shortcuts")
    for scope in root.GetGroups():
        g = root.GetGroup(scope)
        keys = {}
        for pname in g.GetStrings():
            name = g.GetString(pname, "")
            if not name:
                continue
            key, _, gesture = pname.partition(" ")
            if gesture in ("", "tap"):
                gesture = "press"    # the older spelling folds into press
            if gesture not in GESTURES:
                continue
            keys.setdefault(key, {})[gesture] = name
        binds[scope] = keys
    return binds


def set_bind(scope, key, pie_name, gesture="press"):
    _grp("Shortcuts").GetGroup(scope).SetString(_bind_param(key, gesture),
                                                pie_name)


def clear_bind(scope, key, gesture="press"):
    _grp("Shortcuts").GetGroup(scope).RemString(_bind_param(key, gesture))
    if gesture == "press":               # the older spelling of the same thing
        _grp("Shortcuts").GetGroup(scope).RemString(f"{key} tap")


def remove_key(key):
    """Drop a key from every scope at once (the shortcuts-table row delete)."""
    root = _grp("Shortcuts")
    for scope in root.GetGroups():
        for pname in (key, f"{key} double", f"{key} hold",
                      f"{key} double-hold", f"{key} tap"):
            root.GetGroup(scope).RemString(pname)


def get_schema_version():
    return _grp().GetInt("SchemaVersion", 0)


def set_schema_version(v):
    _grp().SetInt("SchemaVersion", int(v))
