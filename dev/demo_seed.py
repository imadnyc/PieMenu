"""Seed the scratch config with the demo set, wiping what was there.

Run against the isolated profile before a demo launch:

    env XDG_{DATA,CONFIG,CACHE}_HOME=... freecadcmd dev/demo_seed.py

Writes V2/SchemaVersion=2 so startup migration leaves the seeds alone.
NEVER run this against a real profile — install_seed.py merges instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("PIEMENU_REPO",
                                  "/home/dre/Projects/PieMenu"))

import FreeCAD as App
from demo_pies import BINDS, build_pies

from piemenu import model

App.ParamGet("User parameter:BaseApp/PieMenu").RemGroup("V2")

pies = build_pies()
pies["Main"].labels_always = True    # Mouse4: always-visible name pills
for pie in pies.values():
    model.save_pie(pie)
for scope, key, name, gesture in BINDS:
    model.set_bind(scope, key, name, gesture)

# demo-only: the mouse side buttons show off the label modes on
# MOUSE_KEYS.  Mouse4 = a click pie with the Labels box ticked;
# Mouse5 = a hover-fire pie, where the pills are forced on (pointing
# at a slot to read it would run it)
hover = build_pies()["Modelling"]    # 12 slots = two rings of pills
hover.name = "HoverLab"
hover.run_on = "hover"
model.save_pie(hover)
model.set_bind(model.ANY_SCOPE, "Mouse4", "Main")
model.set_bind(model.ANY_SCOPE, "Mouse5", "HoverLab")

model.set_schema_version(model.SCHEMA_VERSION)
print("DEMO-SEEDED:", ", ".join(sorted(model.load_pies())))
