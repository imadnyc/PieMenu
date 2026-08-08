"""Headless tests for piemenu.model (the v2 data model).

Run via ``nix run .#smoke`` -- freecadcmd, offscreen, isolated scratch config,
so the ParamGet round-trips exercise the real parameter tree without touching
the user's configuration.
"""
import math
import os
import sys

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from piemenu import model as M
from piemenu.model import Binding, Pie


def approx(a, b, eps=1e-6):
    return abs(a - b) < eps


# ---- rules ---------------------------------------------------------------
r = M.decode_rule("Face>=1;Edge>=1")
assert r == {"Face": (">=", 1), "Edge": (">=", 1)}, r
# canonical encoding follows AXES order, whatever order came in
assert M.encode_rule(r) == "Edge>=1;Face>=1"
assert M.decode_rule("") == {}
assert M.encode_rule({}) == ""
assert M.decode_rule("Object==2") == {"Object": ("==", 2)}
for bad in ("Foo>=1", "Face=>1", "Face>=x", "Face"):
    try:
        M.decode_rule(bad)
        raise AssertionError(f"decode accepted {bad!r}")
    except ValueError:
        pass

assert M.match_rule({}, {})                                   # always
assert M.match_rule({"Face": (">=", 1)}, {"Face": 2})
assert not M.match_rule({"Face": (">=", 1)}, {})              # missing = 0
assert M.match_rule({"Face": ("==", 1)}, {"Face": 1})
assert not M.match_rule({"Face": ("==", 1)}, {"Face": 2})     # Groove case
assert M.match_rule({"Face": (">=", 1), "Edge": (">=", 1)},
                    {"Face": 1, "Edge": 3})                   # Draft case
assert not M.match_rule({"Object": (">=", 2)}, {"Object": 1})
print("PASS rules")

# ---- slots ---------------------------------------------------------------
slot = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
        Binding("PartDesign_Pocket", {"Face": (">=", 1)}),
        Binding("PartDesign_Groove", {"Face": ("==", 1)})]
assert [b.cmd for b in M.live_bindings(slot, {"Face": 1})] == \
    ["PartDesign_Pad", "PartDesign_Pocket", "PartDesign_Groove"]
assert [b.cmd for b in M.live_bindings(slot, {"Face": 2})] == \
    ["PartDesign_Pad", "PartDesign_Pocket"]                   # Groove drops
assert M.live_bindings(slot, {"Edge": 1}) == []
assert M.is_pie_command("PieMenu_View") and M.pie_target("PieMenu_View") == "View"
assert not M.is_pie_command("Std_Undo")
print("PASS slots")

# ---- layout: circle -------------------------------------------------------
c = Pie("C", slots=8, per_ring=8, radius=80, arc=360, arc_face=-90)
pos = M.positions(c)
assert len(pos) == 8
assert approx(pos[0][0], 0) and approx(pos[0][1], -80)        # facing up
half = Pie("H", slots=5, per_ring=5, radius=80, arc=180, arc_face=0)
hp = M.positions(half)
assert approx(hp[0][0], 0) and approx(hp[0][1], -80)          # arc centred on 0deg
assert approx(hp[-1][0], 0) and approx(hp[-1][1], 80)
st = Pie("S", slots=8, per_ring=8, radius=80, stagger=True, stagger_by=40)
sp = M.positions(st)
r0 = (sp[0][0] ** 2 + sp[0][1] ** 2) ** 0.5
r1 = (sp[1][0] ** 2 + sp[1][1] ** 2) ** 0.5
assert approx(r1 - r0, 40)                                    # the knob, exactly
rings = Pie("R", slots=12, per_ring=6, radius=56, button=34, spacing=6)
rp = M.positions(rings)
outer = (rp[6][0] ** 2 + rp[6][1] ** 2) ** 0.5
assert approx(outer, 56 + 34 + 6 + 10)                        # second ring
print("PASS circle layout")

# ---- layout: multi-anchor grid -------------------------------------------
g = Pie("G", family="grid", cols=3, rows=2, radius=80, button=34, spacing=6,
        anchors=["Top", "Bottom", "Right"])
assert M.slot_count(g) == 18
gp = M.positions(g)
assert len(gp) == 18
assert all(y <= -40 for _, y in gp[0:6])                      # block above
assert all(x >= 40 and abs(y) <= 20 for x, y in gp[6:12])     # block right
assert all(y >= 40 for _, y in gp[12:18])                     # block below
M.normalise(g)
assert len(g.items) == 18
g.anchors = ["Center"]
M.normalise(g)
assert len(g.items) == 6
print("PASS grid layout")

# ---- per-anchor offsets ------------------------------------------------------
g2 = Pie("G2", family="grid", cols=2, rows=1, radius=60,
         anchors=["Top", "Bottom"])
M.normalise(g2)
even = M.positions(g2)
g2.anchor_offsets["Bottom"] = 220              # push only the bottom block
far = M.positions(g2)
assert far[0][1] == even[0][1]                 # top block unmoved
assert far[2][1] > even[2][1]                  # bottom block further out
M.save_pie(g2)
assert M.load_pie("G2").anchor_offsets == {"Bottom": 220}
g2.anchor_offsets.clear()
M.save_pie(g2)
assert M.load_pie("G2").anchor_offsets == {}   # cleared offsets stay cleared
M.delete_pie("G2")
print("PASS anchor offsets")

# ---- per-ring counts ---------------------------------------------------------
r3 = Pie("R3", slots=24, per_ring=8, radius=80, spacing=6, button=34,
         ring_mode="custom")
M.normalise(r3)
r3.ring_counts = [8, 16]
assert M.ring_plan(r3) == [8, 16]
rp = M.positions(r3)
radii = [math.hypot(x, y) for x, y in rp]
assert all(abs(r - 80) < 0.01 for r in radii[:8])       # ring one at radius
assert all(r > 80 for r in radii[8:])                   # ring two further out
assert len({round(r, 2) for r in radii[8:]}) == 1       # ...on ONE ring of 16
r3.ring_counts = [8]                                    # last count repeats
assert M.ring_plan(r3) == [8, 8, 8]
r3.ring_counts = []
assert M.ring_plan(r3) == [8, 8, 8]                     # falls back to per_ring
r3.ring_counts = [8, 16]
M.save_pie(r3)
back = M.load_pie("R3")
assert back.ring_counts == [8, 16] and back.ring_mode == "custom"
r3.ring_counts = []
M.save_pie(r3)
assert M.load_pie("R3").ring_counts == []
M.delete_pie("R3")

# auto mode: each ring takes what its circumference fits, outer rings more
r4 = Pie("R4", slots=40, per_ring=8, radius=80, spacing=6, button=34,
         ring_mode="auto")
M.normalise(r4)
auto_plan = M.ring_plan(r4)
assert sum(auto_plan) == 40
assert auto_plan[0] < auto_plan[1]      # the roomier ring holds more
assert M.ring_plan(Pie("U", slots=24, per_ring=8)) == [8, 8, 8]  # uniform
print("PASS ring counts")

# ---- usage stats and the Smart pie ------------------------------------------
M.bump_stat("PartDesign", "A")
M.bump_stat("PartDesign", "A")
M.bump_stat("PartDesign", "B")
M.bump_stat("Sketcher", "C")
M.bump_stat("Sketcher", "C")
M.bump_stat("Sketcher", "C")
assert M.stats("PartDesign") == {"A": 2, "B": 1}
assert M.stats() == {"A": 2, "B": 1, "C": 3}
assert M.top_commands("PartDesign", 8) == ["A", "B", "C"]  # own first
smart = M.smart_pie("PartDesign")
assert smart.name == M.SMART_NAME
assert smart.items[0][0].cmd == "A" and smart.items[2][0].cmd == "C"
base = Pie(M.SMART_NAME, slots=4, per_ring=4, run_on="release", radius=120)
tuned = M.smart_pie("PartDesign", base=base)
assert tuned.run_on == "release" and tuned.radius == 120   # settings kept
assert len(tuned.items) == 4 and tuned.items[0][0].cmd == "A"
assert base.items != tuned.items or base is not tuned      # base untouched

lbl = Pie("Lbl", slots=2, per_ring=2)
M.normalise(lbl)
lbl.items[0] = [Binding("PartDesign_AdditiveLoft", label="Loft")]
M.save_pie(lbl)
assert M.load_pie("Lbl").items[0][0].label == "Loft"       # labels persist
M.delete_pie("Lbl")
M.bump_stat("Any", M.PIE_PREFIX + "Main")
assert M.PIE_PREFIX + "Main" not in M.top_commands("Any", 8)  # no doors

# pinned favorites lead the Smart pie, whatever the usage says
M.set_smart_favorite("Z_Rare", True)
assert M.smart_favorites() == ["Z_Rare"]
sp = M.smart_pie("PartDesign")
assert sp.items[0][0].cmd == "Z_Rare"        # favorite first
assert sp.items[1][0].cmd == "A"             # then the usual ranking
M.set_smart_favorite("Z_Rare", False)
assert M.smart_favorites() == []

# task-panel pseudo-commands need nothing installed
pp = Pie("PP", slots=2, per_ring=2)
M.normalise(pp)
pp.items[0] = [Binding("Panel:OK")]
assert M.pie_requires(pp) == []

# last-fired round trip
M.set_last_fired("Main", "Std_Undo")
assert M.last_fired("Main") == "Std_Undo"
assert M.last_fired("Nowhere") == ""

M.App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("PASS stats + smart")

# ---- pie_requires ------------------------------------------------------------
rq = Pie("Rq", slots=8, per_ring=8)
M.normalise(rq)
rq.items[0] = [Binding("PartDesign_Pad"), Binding("PartDesign_Pocket")]
rq.items[1] = [Binding("Fasteners_Screw", {"Face": (">=", 1)})]
rq.items[2] = [Binding("Std_New")]                    # core: not listed
rq.items[3] = [Binding("PieMenu_Other")]              # door: not listed
rq.items[4] = [Binding("Macro:mine.FCMacro")]         # named outright
rq.items[5] = [Binding("AssemblyWorkbench")]          # wb entry -> Assembly
assert M.pie_requires(rq) == ["Assembly", "Fasteners",
                              "Macro:mine.FCMacro", "PartDesign"]
assert M.pie_requires(Pie("Empty", slots=2, per_ring=2)) == []
big = Pie("Big", slots=48, per_ring=8)
M.normalise(big)
for i in range(48):                                   # stress: many prefixes
    big.items[i] = [Binding(f"Bench{i % 7}_Tool{i}")]
assert len(M.pie_requires(big)) == 7                  # deduped
print("PASS pie requires")

# ---- liveness with cycles -------------------------------------------------
pies = {
    "A": M.normalise(Pie("A", slots=2,
                         items=[[Binding("PieMenu_B")], None])),
    "B": M.normalise(Pie("B", slots=2,
                         items=[[Binding("PieMenu_A")],
                                [Binding("Part_Cut", {"Object": (">=", 2)})]])),
}
assert not M.pie_live("A", pies, {})                          # cycle, no leaf
assert M.pie_live("A", pies, {"Object": 2})                   # leaf via B
assert not M.pie_live("missing", pies, {})
print("PASS liveness")

# ---- shortcut resolution --------------------------------------------------
binds = {"Any": {"9": {"press": "Sketching"}, "0": {"press": "View"}},
         "PartDesign": {"1": {"press": "Main"}, "9": {"press": "Override"}}}
assert M.resolve_key("1", "PartDesign", binds) == ("Main", "PartDesign")
assert M.resolve_key("9", "PartDesign", binds) == ("Override", "PartDesign")
assert M.resolve_key("9", "Sketcher", binds) == ("Sketching", "Any")
assert M.resolve_key("7", "PartDesign", binds) is None

# sketch editing is its own scope, falling back through Sketcher to Any
assert M.scope_chain("PartDesign") == ("PartDesign", "Any")
assert M.scope_chain(M.SKETCH_EDIT_SCOPE) == \
    (M.SKETCH_EDIT_SCOPE, "Sketcher", "Any")
binds["Sketcher"] = {"9": {"press": "SkPie"}}
assert M.resolve_key("9", M.SKETCH_EDIT_SCOPE, binds) == \
    ("SkPie", "Sketcher")
binds[M.SKETCH_EDIT_SCOPE] = {"9": {"press": "EditPie"}}
assert M.resolve_key("9", M.SKETCH_EDIT_SCOPE, binds) == \
    ("EditPie", M.SKETCH_EDIT_SCOPE)
assert M.resolve_key("0", M.SKETCH_EDIT_SCOPE, binds) == ("View", "Any")
print("PASS resolution")

# ---- ParamGet round trip (the part that needs FreeCAD) --------------------
import FreeCAD as App  # only reachable under freecadcmd

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")  # pristine

pie = Pie("Boolean ops", family="grid", icon="bool", cols=2, rows=2,
          anchors=["Top", "Right"], open_on="hold", run_on="release",
          delay=300, stagger_by=25, default=True)
M.normalise(pie)
pie.items[0] = [Binding("Part_Cut", {"Object": (">=", 2)})]
pie.items[2] = [Binding("PieMenu_View"),
                Binding("PartDesign_Pad", {"Face": (">=", 1)})]
M.save_pie(pie)

back = M.load_pie("Boolean ops")
for f in ("name", "family", "icon", "cols", "rows", "anchors", "open_on",
          "run_on", "delay", "stagger_by", "default"):
    assert getattr(back, f) == getattr(pie, f), (f, getattr(back, f))
assert back.items[0][0].cmd == "Part_Cut"
assert back.items[0][0].rule == {"Object": (">=", 2)}
assert [b.cmd for b in back.items[2]] == ["PieMenu_View", "PartDesign_Pad"]
assert back.items[2][1].rule == {"Face": (">=", 1)}
assert back.items[1] is None and back.items[3] is None

# saving again with a slot cleared must not resurrect old bindings
pie.items[0] = None
M.save_pie(pie)
assert M.load_pie("Boolean ops").items[0] is None

assert "Boolean ops" in M.load_pies()
M.delete_pie("Boolean ops")
assert "Boolean ops" not in M.load_pies()
print("PASS pie IO")

# ---- shortcut IO: a binding is key x scope x gesture -----------------------
M.set_bind("Any", "9", "Sketching")
M.set_bind("PartDesign", "1", "Main")
M.set_bind("PartDesign", "Ctrl+1", "Modelling")   # modifier keys as param names
M.set_bind("Sketcher", "1", "Main")
M.set_bind("PartDesign", "1", "Patterns", "double")
M.set_bind("Any", "1", "View", "hold")
M.set_bind("Any", "1", "Datums", "double-hold")
b2 = M.load_binds()
assert b2["Any"]["9"] == {"press": "Sketching"}
assert b2["PartDesign"]["Ctrl+1"] == {"press": "Modelling"}
assert b2["PartDesign"]["1"] == {"press": "Main", "double": "Patterns"}
assert b2["Any"]["1"] == {"hold": "View", "double-hold": "Datums"}
assert M.resolve_key("Ctrl+1", "PartDesign", b2) == ("Modelling", "PartDesign")
assert M.resolve_key("1", "PartDesign", b2, "double") == \
    ("Patterns", "PartDesign")
# each gesture inherits independently through the Any scope
assert M.gestures_for("1", "PartDesign", b2) == {
    "press": ("Main", "PartDesign"),
    "double": ("Patterns", "PartDesign"),
    "hold": ("View", "Any"),
    "double-hold": ("Datums", "Any")}
assert M.gestures_for("1", "Sketcher", b2) == {
    "press": ("Main", "Sketcher"),
    "hold": ("View", "Any"),
    "double-hold": ("Datums", "Any")}
assert M.key_gestures("1", b2) == ["press", "double", "hold", "double-hold"]
assert M.key_gestures("9", b2) == ["press"]
M.remove_key("1")
b3 = M.load_binds()
assert "1" not in b3.get("PartDesign", {}) and "1" not in b3.get("Sketcher", {})
assert "1" not in b3.get("Any", {})               # the legacy hold went too
M.clear_bind("Any", "9")
assert "9" not in M.load_binds().get("Any", {})

M.set_schema_version(2)
assert M.get_schema_version() == 2
App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")  # leave no trace
print("PASS shortcut IO")

# ---- slot faces and sticky picks -------------------------------------------
slot = [M.Binding("A"), M.Binding("B")]
assert M.slot_face(slot, {}).cmd == "A"
assert M.slot_face(slot, {}, "B").cmd == "B"          # a pick moves the face
assert M.slot_face(slot, {}, "Z").cmd == "A"          # a stale pick falls back
gated = [M.Binding("A", {"Face": (">=", 1)}), M.Binding("B")]
assert M.slot_face(gated, {}, "A").cmd == "B"         # pick no longer applies
assert M.slot_face([M.Binding("A", {"Face": (">=", 1)})], {}) is None

# the context checker: conditional + always mixed in one slot is flagged
mixed = [M.Binding("A", {"Object": (">=", 2)}), M.Binding("B")]
assert [i for i, _ in M.slot_check(mixed)] == [1]     # the always-on culprit
assert M.slot_check([M.Binding("A"), M.Binding("B")]) == []   # pure overload
assert M.slot_check([M.Binding("A", {"Face": (">=", 1)}),
                     M.Binding("B", {"Edge": (">=", 1)})]) == []
assert M.slot_check(None) == [] and M.slot_check([]) == []

sticky = M.Pie("Sticky", slots=2, per_ring=2, alt_size=40, door_hover=False)
M.normalise(sticky)
sticky.items[0] = [M.Binding("A"), M.Binding("B")]
sticky.last_used[0] = "B"
M.save_pie(sticky)
M.set_last_used("Sticky", 0, "A")                     # the targeted setter
back = M.load_pie("Sticky")
assert back.last_used == {0: "A"}
assert back.alt_size == 40 and back.door_hover is False
M.delete_pie("Sticky")
App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("PASS slot face")

print("MODEL-TESTS-PASS")
