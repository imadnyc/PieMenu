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

# two rings: 8 inner, 4 outer -- the second ring is the deeper PartDesign kit
modelling = Pie("Modelling", slots=12, per_ring=8, radius=90,
                open_on="hold", run_on="release")
model.normalise(modelling)
modelling.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                      Binding("PartDesign_Pocket", {"Face": (">=", 1)}),
                      Binding("PartDesign_Groove", {"Face": ("==", 1)})]
modelling.items[1] = [Binding("PartDesign_Fillet", {"Edge": (">=", 1)}),
                      Binding("PartDesign_Chamfer", {"Edge": (">=", 1)}),
                      Binding("PartDesign_Thickness", {"Face": (">=", 2)})]
modelling.items[2] = [Binding("Part_Cut", {"Object": (">=", 2)})]
modelling.items[3] = [Binding("PartDesign_Draft",
                              {"Face": (">=", 1), "Edge": (">=", 1)})]
modelling.items[4] = [Binding("PartDesign_Revolution", {"Face": (">=", 1)})]
modelling.items[5] = [Binding("Std_Redo")]
modelling.items[6] = [Binding("PieMenu_Patterns")]
modelling.items[7] = [Binding("PieMenu_Datums")]
modelling.items[8] = [Binding("PartDesign_AdditiveLoft"),
                      Binding("PartDesign_SubtractiveLoft")]
modelling.items[9] = [Binding("PartDesign_AdditivePipe")]
modelling.items[10] = [Binding("PartDesign_Hole", {"Face": (">=", 1)})]
modelling.items[11] = [Binding("PartDesign_Boolean", {"Object": (">=", 2)})]

patterns = Pie("Patterns", slots=4, per_ring=4, radius=70)
model.normalise(patterns)
patterns.items[0] = [Binding("PartDesign_Mirrored")]
patterns.items[1] = [Binding("PartDesign_LinearPattern")]
patterns.items[2] = [Binding("PartDesign_PolarPattern")]
patterns.items[3] = [Binding("PartDesign_MultiTransform")]

sketching = Pie("Sketching", family="grid", cols=3, rows=2, radius=80,
                anchors=["Top", "Bottom"])
model.normalise(sketching)
for i, cmd in enumerate(("Sketcher_NewSketch", "Sketcher_CreateLine",
                         "Sketcher_CreateCircle", "Sketcher_CreateRectangle",
                         "Sketcher_CreateArc", "Sketcher_CreatePolyline")):
    sketching.items[i] = [Binding(cmd)]
sketching.items[6] = [Binding("PieMenu_Constraints")]

constraints = Pie("Constraints", slots=8, per_ring=8, radius=90,
                  open_on="hold", run_on="release")
model.normalise(constraints)
for i, cmd in enumerate(("Sketcher_ConstrainCoincident",
                         "Sketcher_ConstrainHorizontal",
                         "Sketcher_ConstrainVertical")):
    constraints.items[i] = [Binding(cmd)]
# one Distance slot, three flavours: the chooser picks the axis
constraints.items[3] = [Binding("Sketcher_ConstrainDistance"),
                        Binding("Sketcher_ConstrainDistanceX"),
                        Binding("Sketcher_ConstrainDistanceY")]
for i, cmd in enumerate(("Sketcher_ConstrainParallel",
                         "Sketcher_ConstrainPerpendicular",
                         "Sketcher_ConstrainTangent",
                         "Sketcher_ConstrainEqual"), start=4):
    constraints.items[i] = [Binding(cmd)]

booleans = Pie("Booleans", slots=6, per_ring=6, radius=80)
model.normalise(booleans)
booleans.items[0] = [Binding("Part_Fuse", {"Object": (">=", 2)})]
booleans.items[1] = [Binding("Part_Cut", {"Object": (">=", 2)})]
booleans.items[2] = [Binding("Part_Common", {"Object": (">=", 2)})]
booleans.items[3] = [Binding("Part_Section", {"Object": (">=", 2)})]
booleans.items[4] = [Binding("Part_CheckGeometry", {"Object": (">=", 1)})]
booleans.items[5] = [Binding("Part_RefineShape", {"Object": (">=", 1)})]

datums = Pie("Datums", slots=6, per_ring=6, radius=80)
model.normalise(datums)
for i, cmd in enumerate(("PartDesign_Plane", "PartDesign_Line",
                         "PartDesign_Point", "PartDesign_CoordinateSystem",
                         "PartDesign_ShapeBinder", "Std_Placement")):
    datums.items[i] = [Binding(cmd)]

view = Pie("View", slots=6, per_ring=6, radius=75, default=True)
model.normalise(view)
for i, cmd in enumerate(("Std_ViewFitAll", "Std_ViewFront", "Std_ViewTop",
                         "Std_ViewRight", "Std_ViewIsometric",
                         "Std_ViewScreenShot")):
    view.items[i] = [Binding(cmd)]

for pie in (main, modelling, patterns, sketching, view,
            constraints, booleans, datums):
    model.save_pie(pie)

# F3-F8, skipping F5 (FreeCAD recompute; F1 help and F2 rename also taken).
# F3 and F7 are scoped -- one key, per-workbench meaning; the rest are direct.
model.set_bind(ANY_SCOPE, "F3", "Main")
model.set_bind("PartDesign", "F3", "Modelling")
model.set_bind("Sketcher", "F3", "Sketching")
model.set_bind(ANY_SCOPE, "F4", "Modelling")
model.set_bind(ANY_SCOPE, "F6", "View")
model.set_bind(ANY_SCOPE, "F7", "Booleans")
model.set_bind("Sketcher", "F7", "Constraints")
model.set_bind(ANY_SCOPE, "F8", "Datums")

model.set_schema_version(model.SCHEMA_VERSION)
print("DEMO-SEEDED:", ", ".join(sorted(model.load_pies())))
