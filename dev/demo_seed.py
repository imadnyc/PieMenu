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

for pie in build_pies().values():
    model.save_pie(pie)
for scope, key, name, gesture in BINDS:
    model.set_bind(scope, key, name, gesture)

# demo-only: the mouse side buttons drive pies too (full gestures --
# tap opens, hold marks), so the scratch GUI shows off MOUSE_KEYS
model.set_bind(model.ANY_SCOPE, "Mouse4", "Main")
model.set_bind(model.ANY_SCOPE, "Mouse5", "Modelling")

model.set_schema_version(model.SCHEMA_VERSION)
print("DEMO-SEEDED:", ", ".join(sorted(model.load_pies())))
