"""Headless tests for piemenu.model (the v2 data model).

Run via ``nix run .#smoke`` -- freecadcmd, offscreen, isolated scratch config,
so the ParamGet round-trips exercise the real parameter tree without touching
the user's configuration.
"""
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
binds = {"Any": {"9": "Sketching", "0": "View"},
         "PartDesign": {"1": "Main", "9": "Override"}}
assert M.resolve_key("1", "PartDesign", binds) == ("Main", "PartDesign")
assert M.resolve_key("9", "PartDesign", binds) == ("Override", "PartDesign")
assert M.resolve_key("9", "Sketcher", binds) == ("Sketching", "Any")
assert M.resolve_key("7", "PartDesign", binds) is None
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

# ---- shortcut IO ----------------------------------------------------------
M.set_bind("Any", "9", "Sketching")
M.set_bind("PartDesign", "1", "Main")
M.set_bind("PartDesign", "Ctrl+1", "Modelling")   # modifier keys as param names
M.set_bind("Sketcher", "1", "Main")
b2 = M.load_binds()
assert b2["Any"]["9"] == "Sketching"
assert b2["PartDesign"]["Ctrl+1"] == "Modelling"
assert M.resolve_key("Ctrl+1", "PartDesign", b2) == ("Modelling", "PartDesign")
M.remove_key("1")
b3 = M.load_binds()
assert "1" not in b3.get("PartDesign", {}) and "1" not in b3.get("Sketcher", {})
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

sticky = M.Pie("Sticky", slots=2, per_ring=2)
M.normalise(sticky)
sticky.items[0] = [M.Binding("A"), M.Binding("B")]
sticky.last_used[0] = "B"
M.save_pie(sticky)
M.set_last_used("Sticky", 0, "A")                     # the targeted setter
back = M.load_pie("Sticky")
assert back.last_used == {0: "A"}
M.delete_pie("Sticky")
App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")
print("PASS slot face")

print("MODEL-TESTS-PASS")
