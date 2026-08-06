"""Headless tests for the v1 -> v2 migration.  Runs under freecadcmd via
``nix run .#smoke`` against an isolated scratch config."""
import os
import sys

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

import FreeCAD as App

from piemenu import migrate, model

ROOT = App.ParamGet("User parameter:BaseApp/PieMenu")
INDEX = App.ParamGet("User parameter:BaseApp/PieMenu/Index")


def reset():
    ROOT.RemGroup("V2")
    ROOT.RemGroup("Index")
    for s in range(1, 10):
        ROOT.RemString(migrate._slot_key(s))
    ROOT.RemString("CurrentPie")
    ROOT.RemString("GlobalShortcutKey")


def seed_pie(i, name, shape, tools, **kw):
    INDEX.SetString(str(i), name)
    g = INDEX.GetGroup(str(i))
    g.SetString("Shape", shape)
    g.SetString("ToolList", ".,.".join(tools))
    for k, v in kw.items():
        (g.SetInt if isinstance(v, int) else g.SetString)(k, v)
    return g


# ---- a realistic legacy tree ----------------------------------------------
reset()
INDEX.SetString("IndexList", "0.,.1.,.2.,.0")          # duplicate on purpose

g0 = seed_pie(0, "Main", "Pie",
              ["Std_New", "PieMenu_Separator", "Std_Save", "PartDesign_Pad"],
              Radius=95, Button=40, ShortcutKey="TAB")
t = g0.GetGroup("Tools").GetGroup("PartDesign_Pad")
t.SetBool("ContextEnabled", True)
t.SetString("FaceSign", ">=")
t.SetInt("FaceValue", 1)
t.SetInt("Slot", 3)

seed_pie(1, "Modelling", "Star", ["PartDesign_Pad", "PartDesign_Pocket"],
         DefaultWorkbench="PartDesign", ShortcutSlot=1,
         TriggerMode="Hover", HoverDelay=400)
seed_pie(2, "Tables", "UpDown",
         ["Std_Undo", "Std_Redo", "Std_Cut", "Std_Paste"], NumColumn=2)

ROOT.SetString("GlobalShortcutKey", "Space")
ROOT.SetString("CurrentPie", "Main")

assert migrate.migrate() is True
assert migrate.migrate() is False                      # idempotent
assert model.get_schema_version() == 2

pies = model.load_pies()
assert set(pies) == {"Main", "Modelling", "Tables"}, set(pies)

m = pies["Main"]
assert m.family == "circle" and m.radius == 95 and m.button == 40
assert m.default is True
assert m.items[0][0].cmd == "Std_New"
assert m.items[1] is None                              # the separator's gap
assert m.items[2][0].cmd == "Std_Save"
assert m.items[3][0].cmd == "PartDesign_Pad"           # explicit Slot wins
assert m.items[3][0].rule == {"Face": (">=", 1)}       # dense -> sparse

s = pies["Modelling"]
assert s.family == "circle" and s.stagger is True      # Star
assert s.run_on == "hover" and s.delay == 400          # TriggerMode=Hover

tb = pies["Tables"]
assert tb.family == "grid" and tb.anchors == ["Top", "Bottom"]
assert tb.cols == 2 and model.slot_count(tb) >= 4

binds = model.load_binds()
assert binds[model.ANY_SCOPE]["TAB"] == {"tap": "Main"}   # the pie's own key
assert binds[model.ANY_SCOPE]["Space"] == {"tap": "Main"}   # global fallback
assert binds["PartDesign"]["Space"] == {"tap": "Modelling"}   # wb override
assert model.resolve_key("Space", "PartDesign", binds) == ("Modelling", "PartDesign")
assert model.resolve_key("Space", "Sketcher", binds) == ("Main", model.ANY_SCOPE)
print("PASS migration")

# ---- fresh install --------------------------------------------------------
reset()
assert migrate.migrate() is True
pies = model.load_pies()
assert list(pies) == ["Main"] and pies["Main"].default
assert pies["Main"].items[0][0].cmd == "Std_New"
assert model.resolve_key("F3", "PartDesign", model.load_binds())[0] == "Main"
print("PASS fresh install")

reset()
print("MIGRATE-TESTS-PASS")
