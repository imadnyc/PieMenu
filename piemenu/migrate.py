"""One-time migration of the v1 parameter tree to the v2 model.

v1 (``…/PieMenu/Index``): ``IndexList`` names pie indices; the string param
``<i>`` holds the pie name and the group ``<i>/`` its settings — ``ToolList``
(".,."-joined commands), ``Shape`` (one of eleven), ``Radius``, ``Button``,
``NumColumn``, ``IconSpacing``, ``TriggerMode`` (Press|Hover), ``HoverDelay``,
``ShortcutKey`` (the pie's own key), ``ShortcutSlot`` + ``DefaultWorkbench``
(which global key it answers, and where), and ``Tools/<command>/`` per-tool
attributes (Slot, ContextEnabled, ``<Axis>Sign``/``<Axis>Value``).

The mapping follows UI-FEEDBACK.md:

- eleven shapes fold into two families (#16);
- per-tool dense context rules become sparse per-binding rules (#29);
- global slots + per-pie workbench assignment become workbench-scoped binds,
  a pie's own ShortcutKey becomes an Any-scope bind (#27/E);
- ``PieMenu_Separator`` entries become empty slots (gaps are first-class);
- the legacy pie-level auto-open context trigger is NOT migrated — that is
  the recorded open question ("Global context" placeholder).

Additive and idempotent: writes only under ``…/PieMenu/V2``, guarded by
``V2/SchemaVersion``.  A fresh install (no v1 pies) gets a small starter pie.
"""

import math

import FreeCAD as App

from . import model
from .model import ANY_SCOPE, AXES, Binding, Pie

V1_MAIN = "User parameter:BaseApp/PieMenu"
V1_INDEX = "User parameter:BaseApp/PieMenu/Index"
SEPARATOR = "PieMenu_Separator"


def _index_list(index):
    raw = index.GetString("IndexList")
    seen, out = set(), []
    for value in filter(None, raw.split(".,.")):
        try:
            i = int(value)
        except ValueError:
            continue
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _slot_key(slot):
    return "GlobalShortcutKey" if slot <= 1 else f"GlobalShortcutKey{slot}"


def _tool_rule(tools_group, command):
    """The per-tool dense context rule as a sparse v2 rule."""
    if tools_group is None or command not in tools_group.GetGroups():
        return {}
    g = tools_group.GetGroup(command)
    if not g.GetBool("ContextEnabled", False):
        return {}
    rule = {}
    for axis in AXES:
        sign = g.GetString(axis + "Sign", "")
        if sign in model._SIGNS:
            rule[axis] = (sign, g.GetInt(axis + "Value", 0))
    return rule


def _shape_to_layout(pie, shape, n, num_column):
    """Fold the eleven v1 shapes into the two v2 families (#16)."""
    cols = max(1, num_column) if num_column else 3
    if shape in ("TableTop", "TableDown", "TableLeft", "TableRight",
                 "UpDown", "LeftRight"):
        pie.family = "grid"
        anchors = {"TableTop": ["Top"], "TableDown": ["Bottom"],
                   "TableLeft": ["Left"], "TableRight": ["Right"],
                   "UpDown": ["Top", "Bottom"],
                   "LeftRight": ["Left", "Right"]}[shape]
        pie.anchors = anchors
        pie.cols = cols
        pie.rows = max(1, math.ceil(n / (cols * len(anchors))))
        return
    pie.family = "circle"
    pie.slots = max(1, n)
    pie.per_ring = pie.slots
    if shape == "Concentric":
        pie.per_ring = max(1, num_column) if num_column else min(8, pie.slots)
    elif shape == "Star":
        pie.stagger = True
    elif shape == "RainbowUp":
        pie.arc, pie.arc_face = 180, -90
    elif shape == "RainbowDown":
        pie.arc, pie.arc_face = 180, 90
    # "Pie" and anything unknown: the defaults (full circle facing up)


def _migrate_pie(index, i):
    name = index.GetString(str(i))
    if not name:
        return None
    g = index.GetGroup(str(i))
    tools = [t for t in g.GetString("ToolList").split(".,.") if t]
    tools_group = g.GetGroup("Tools") if "Tools" in g.GetGroups() else None

    pie = Pie(name=name)
    _shape_to_layout(pie, g.GetString("Shape", "Pie"), max(1, len(tools)),
                     g.GetInt("NumColumn", 0))
    if g.GetInt("Radius", 0):
        pie.radius = g.GetInt("Radius", 0)
    if g.GetInt("Button", 0):
        pie.button = g.GetInt("Button", 0)
    if g.GetInt("IconSpacing", -1) >= 0:
        pie.spacing = g.GetInt("IconSpacing", 0)
    if g.GetString("TriggerMode", "Press") == "Hover":
        pie.run_on = "hover"
        pie.delay = g.GetInt("HoverDelay", 0) or pie.delay

    model.normalise(pie)
    # ToolList order fills the slots; an explicit per-tool Slot wins, and two
    # tools claiming one slot stack as ordered bindings (an overloaded slot)
    cursor = 0
    for cmd in tools:
        if cmd == SEPARATOR:
            cursor += 1
            continue
        slot = -1
        if tools_group is not None and cmd in tools_group.GetGroups():
            slot = tools_group.GetGroup(cmd).GetInt("Slot", -1)
        if slot < 0 or slot >= len(pie.items):
            while cursor < len(pie.items) and pie.items[cursor]:
                cursor += 1
            slot = min(cursor, len(pie.items) - 1)
            cursor += 1
        binding = Binding(cmd, _tool_rule(tools_group, cmd))
        if pie.items[slot]:
            pie.items[slot].append(binding)
        else:
            pie.items[slot] = [binding]
    return pie, g


def _starter_pie():
    pie = Pie(name="Main", slots=6, per_ring=6)
    model.normalise(pie)
    for i, cmd in enumerate(("Std_New", "Std_Open", "Std_Save",
                             "Std_Undo", "Std_Redo", "Std_Refresh")):
        pie.items[i] = [Binding(cmd)]
    return pie


def migrate():
    """Run the v1 -> v2 migration once.  Returns True when it did any work."""
    if model.get_schema_version() >= model.SCHEMA_VERSION:
        return False

    main = App.ParamGet(V1_MAIN)
    index = App.ParamGet(V1_INDEX)

    migrated = []           # (pie, v1 group)
    for i in _index_list(index):
        got = _migrate_pie(index, i)
        if got:
            migrated.append(got)

    if not migrated:
        starter = _starter_pie()
        starter.default = True
        model.save_pie(starter)
        key = main.GetString("GlobalShortcutKey", "") or "F3"
        model.set_bind(ANY_SCOPE, key, starter.name)
        model.set_schema_version(model.SCHEMA_VERSION)
        return True

    # the fallback pie: what the old code showed when nothing matched
    default_name = main.GetString("CurrentPie", "") or migrated[0][0].name
    if default_name not in [p.name for p, _ in migrated]:
        default_name = migrated[0][0].name

    binds_taken = set()
    for pie, g in migrated:
        pie.default = pie.name == default_name
        model.save_pie(pie)

        # the pie's own key: context-free, so it lands in the Any scope
        own = g.GetString("ShortcutKey", "")
        if own and (ANY_SCOPE, own) not in binds_taken:
            model.set_bind(ANY_SCOPE, own, pie.name)
            binds_taken.add((ANY_SCOPE, own))

    # global slots: each key opens the assigned pie in its workbench, and the
    # fallback pie everywhere else
    for slot in range(1, 10):
        key = main.GetString(_slot_key(slot), "")
        if not key:
            continue
        if (ANY_SCOPE, key) not in binds_taken:
            model.set_bind(ANY_SCOPE, key, default_name)
            binds_taken.add((ANY_SCOPE, key))
        for pie, g in migrated:
            wb = g.GetString("DefaultWorkbench", "")
            if (wb and wb != "None" and g.GetInt("ShortcutSlot", 1) == slot
                    and (wb, key) not in binds_taken):
                model.set_bind(wb, key, pie.name)
                binds_taken.add((wb, key))

    model.set_schema_version(model.SCHEMA_VERSION)
    return True
