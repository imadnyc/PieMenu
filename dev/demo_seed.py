"""Seed the scratch config with a demo set that exercises the whole v2 model.

Run against the isolated profile before a demo launch:

    env XDG_{DATA,CONFIG,CACHE}_HOME=... freecadcmd dev/demo_seed.py

Real command names throughout, so everything actually fires.  Writes
V2/SchemaVersion=2 so startup migration leaves the seeds alone.
"""
import os
import sys

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

import FreeCAD as App

from piemenu import model
from piemenu.model import ANY_SCOPE, Binding, Pie

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")

main = Pie("Main", slots=8, per_ring=8, radius=95)
model.normalise(main)
main.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                 Binding("PartDesign_Fillet", {"Edge": (">=", 1)}),
                 Binding("PartDesign_Chamfer", {"Edge": (">=", 1)})]
main.items[1] = [Binding("Std_New")]
main.items[2] = [Binding("Std_Save")]
# one slot, two pies: which door opens depends on the selection
main.items[3] = [Binding("PieMenu_Modelling", {"Face": (">=", 1)}),
                 Binding("PieMenu_Sketching", {"Edge": (">=", 1)})]
main.items[4] = [Binding("Std_Undo")]
main.items[5] = [Binding("PieMenu_View")]

modelling = Pie("Modelling", slots=8, per_ring=8, radius=90,
                open_on="hold", run_on="release")
model.normalise(modelling)
modelling.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                      Binding("PartDesign_Pocket", {"Face": (">=", 1)}),
                      Binding("PartDesign_Groove", {"Face": ("==", 1)})]
modelling.items[1] = [Binding("PartDesign_Fillet", {"Edge": (">=", 1)}),
                      Binding("PartDesign_Thickness", {"Face": (">=", 2)})]
modelling.items[2] = [Binding("Part_Cut", {"Object": (">=", 2)})]
modelling.items[3] = [Binding("PartDesign_Draft",
                              {"Face": (">=", 1), "Edge": (">=", 1)})]
modelling.items[4] = [Binding("PartDesign_Revolution", {"Face": (">=", 1)})]
modelling.items[5] = [Binding("Std_Redo")]
modelling.items[6] = [Binding("PieMenu_Patterns")]

patterns = Pie("Patterns", slots=4, per_ring=4, radius=70)
model.normalise(patterns)
patterns.items[0] = [Binding("PartDesign_Mirrored")]
patterns.items[1] = [Binding("PartDesign_LinearPattern")]
patterns.items[2] = [Binding("PartDesign_PolarPattern")]

sketching = Pie("Sketching", family="grid", cols=3, rows=2, radius=80,
                anchors=["Top", "Bottom"])
model.normalise(sketching)
for i, cmd in enumerate(("Sketcher_NewSketch", "Sketcher_CreateLine",
                         "Sketcher_CreateCircle", "Sketcher_CreateRectangle",
                         "Sketcher_CreateArc", "Sketcher_CreatePolyline")):
    sketching.items[i] = [Binding(cmd)]

view = Pie("View", slots=6, per_ring=6, radius=75, default=True)
model.normalise(view)
for i, cmd in enumerate(("Std_ViewFitAll", "Std_ViewFront", "Std_ViewTop",
                         "Std_ViewRight", "Std_ViewIsometric",
                         "Std_ViewScreenShot")):
    view.items[i] = [Binding(cmd)]

for pie in (main, modelling, patterns, sketching, view):
    model.save_pie(pie)

# The primary key is scoped: Main everywhere, but the Modelling pie inside
# PartDesign and the Sketching pie inside Sketcher -- one key, three meanings,
# by workbench.  Ctrl+Shift+M is a direct line to Modelling from anywhere.
model.set_bind(ANY_SCOPE, "Ctrl+Shift+P", "Main")
model.set_bind("PartDesign", "Ctrl+Shift+P", "Modelling")
model.set_bind("Sketcher", "Ctrl+Shift+P", "Sketching")
model.set_bind(ANY_SCOPE, "Ctrl+Shift+M", "Modelling")
model.set_bind(ANY_SCOPE, "F6", "View")

model.set_schema_version(model.SCHEMA_VERSION)
print("DEMO-SEEDED:", ", ".join(sorted(model.load_pies())))
