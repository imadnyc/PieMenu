"""Build the playground document for exercising selection contexts.

Runs headless under freecadcmd; writes PieMenuPlayground.FCStd into
``$PIEMENU_DEV/docs``.  The launcher opens it automatically, so every rule
axis has something real to click:

- Body "Box": a padded rectangle -- faces (Face rules), edges (Fillet vs
  Chamfer chooser), vertices.
- Body "Cylinder": a second solid -- select both bodies in the tree for
  Object >= 2 rules (Part booleans, PartDesign_Boolean).
- "LooseSketch": unconstrained lines + circle; double-click to edit, then
  pick endpoints/edges inside it for the Constraints pie's rules.
"""
import os

import FreeCAD as App
import Part

V = App.Vector
OUT = os.path.join(os.environ.get("PIEMENU_DEV", "/tmp/piemenu-dev"), "docs")


def rectangle(sk, x0, y0, w, h):
    pts = [V(x0, y0, 0), V(x0 + w, y0, 0), V(x0 + w, y0 + h, 0),
           V(x0, y0 + h, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)


doc = App.newDocument("PieMenuPlayground")

box = doc.addObject("PartDesign::Body", "Box")
profile = box.newObject("Sketcher::SketchObject", "BoxProfile")
rectangle(profile, 0, 0, 20, 20)
pad = box.newObject("PartDesign::Pad", "BoxPad")
pad.Profile = profile
pad.Length = 12

cyl = doc.addObject("PartDesign::Body", "Cylinder")
cprofile = cyl.newObject("Sketcher::SketchObject", "CylProfile")
cprofile.addGeometry(Part.Circle(V(45, 10, 0), V(0, 0, 1), 8), False)
cpad = cyl.newObject("PartDesign::Pad", "CylPad")
cpad.Profile = cprofile
cpad.Length = 18

loose = doc.addObject("Sketcher::SketchObject", "LooseSketch")
loose.Placement.Base = V(-45, 0, 0)
loose.addGeometry(Part.LineSegment(V(0, 0, 0), V(25, 0, 0)), False)
loose.addGeometry(Part.LineSegment(V(25, 0, 0), V(30, 18, 0)), False)
loose.addGeometry(Part.LineSegment(V(2, 22, 0), V(18, 30, 0)), False)
loose.addGeometry(Part.Circle(V(10, 12, 0), V(0, 0, 1), 5), False)

doc.recompute()
errors = [o.Name for o in doc.Objects if "Error" in getattr(o, "State", [])]
assert not errors, f"recompute failed for {errors}"

os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "PieMenuPlayground.FCStd")
doc.saveAs(path)
print(f"DOCS-BUILT: {path}", flush=True)
