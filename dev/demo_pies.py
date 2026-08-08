"""The demo/starter set: eight pies and the F3-F9 binds, as data.

Used by demo_seed.py (wipe-and-seed for the isolated dev profile) and by
install_seed.py (merge into a real profile without touching anything the
user already has). Real command names throughout, so everything fires.
"""
from piemenu import model
from piemenu.model import ANY_SCOPE, Binding, Pie


def build_pies():
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

    # two rings: 8 inner, 4 outer -- the second ring is the deeper kit
    modelling = Pie("Modelling", slots=12, per_ring=8, radius=90,
                    run_on="release")
    model.normalise(modelling)
    modelling.items[0] = [Binding("PartDesign_Pad", {"Face": (">=", 1)}),
                          Binding("PartDesign_Pocket", {"Face": (">=", 1)}),
                          Binding("PartDesign_Groove", {"Face": ("==", 1)})]
    modelling.items[1] = [Binding("PartDesign_Fillet", {"Edge": (">=", 1)}),
                          Binding("PartDesign_Chamfer", {"Edge": (">=", 1)}),
                          Binding("PartDesign_Thickness",
                                  {"Face": (">=", 2)})]
    modelling.items[2] = [Binding("Part_Cut", {"Object": (">=", 2)})]
    modelling.items[3] = [Binding("PartDesign_Draft",
                                  {"Face": (">=", 1), "Edge": (">=", 1)})]
    modelling.items[4] = [Binding("PartDesign_Revolution",
                                  {"Face": (">=", 1)})]
    modelling.items[5] = [Binding("Std_Redo")]
    modelling.items[6] = [Binding("PieMenu_Patterns")]
    modelling.items[7] = [Binding("PieMenu_Datums")]
    modelling.items[8] = [Binding("PartDesign_AdditiveLoft"),
                          Binding("PartDesign_SubtractiveLoft")]
    modelling.items[9] = [Binding("PartDesign_AdditivePipe")]
    modelling.items[10] = [Binding("PartDesign_Hole", {"Face": (">=", 1)})]
    modelling.items[11] = [Binding("PartDesign_Boolean",
                                   {"Object": (">=", 2)})]

    patterns = Pie("Patterns", slots=4, per_ring=4, radius=70)
    model.normalise(patterns)
    patterns.items[0] = [Binding("PartDesign_Mirrored")]
    patterns.items[1] = [Binding("PartDesign_LinearPattern")]
    patterns.items[2] = [Binding("PartDesign_PolarPattern")]
    patterns.items[3] = [Binding("PartDesign_MultiTransform")]

    sketching = Pie("Sketching", family="grid", cols=3, rows=2, radius=80,
                    anchors=["Top", "Bottom"], run_on="release")
    model.normalise(sketching)
    for i, cmd in enumerate(("Sketcher_NewSketch", "Sketcher_CreateLine",
                             "Sketcher_CreateCircle",
                             "Sketcher_CreateRectangle",
                             "Sketcher_CreateArc",
                             "Sketcher_CreatePolyline")):
        sketching.items[i] = [Binding(cmd)]
    sketching.items[6] = [Binding("PieMenu_Constraints")]

    constraints = Pie("Constraints", slots=8, per_ring=8, radius=90,
                      run_on="release")
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
                             "PartDesign_Point",
                             "PartDesign_CoordinateSystem",
                             "PartDesign_ShapeBinder", "Std_Placement")):
        datums.items[i] = [Binding(cmd)]

    view = Pie("View", slots=6, per_ring=6, radius=75, default=True)
    model.normalise(view)
    for i, cmd in enumerate(("Std_ViewFitAll", "Std_ViewFront",
                             "Std_ViewTop", "Std_ViewRight",
                             "Std_ViewIsometric", "Std_ViewScreenShot")):
        view.items[i] = [Binding(cmd)]

    return {p.name: p for p in (main, modelling, patterns, sketching, view,
                                constraints, booleans, datums)}


# F3-F9, skipping F5 (FreeCAD recompute; F1 help and F2 rename also taken).
# Gesture pies (run_on release) follow the aim and vanish with the key;
# the rest stay open for clicking. In PartDesign F3 does three things:
# tap = Main (inherited), hold = Modelling, double-tap-and-hold = Patterns.
BINDS = [
    (ANY_SCOPE, "F3", "Main", "press"),
    ("PartDesign", "F3", "Modelling", "hold"),
    ("PartDesign", "F3", "Patterns", "double-hold"),
    ("Sketcher", "F3", "Sketching", "hold"),
    # inside sketch editing, tapping F3 goes straight to constraints
    ("SketchEdit", "F3", "Constraints", "press"),
    (ANY_SCOPE, "F4", "Modelling", "press"),
    (ANY_SCOPE, "F4", "Patterns", "double"),
    (ANY_SCOPE, "F6", "View", "press"),
    (ANY_SCOPE, "F7", "Booleans", "press"),
    ("Sketcher", "F7", "Constraints", "hold"),
    (ANY_SCOPE, "F8", "Datums", "press"),
    (ANY_SCOPE, "F9", "Smart", "press"),   # your most-used, per workbench
]
