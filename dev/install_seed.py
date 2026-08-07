"""Merge the starter pies and binds into the CURRENT profile, additively.

    freecadcmd dev/install_seed.py        # against the real profile

Nothing existing is touched: a pie name already in use is skipped, a
key+gesture already bound in a scope is skipped, and the schema version
is only stamped when it is unset. Back up user.cfg first anyway.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("PIEMENU_REPO",
                                  "/home/dre/Projects/PieMenu"))

from demo_pies import BINDS, build_pies

from piemenu import model

existing = model.load_pies()
added, skipped = [], []
for name, pie in build_pies().items():
    if name in existing:
        skipped.append(name)
    else:
        model.save_pie(pie)
        added.append(name)

binds = model.load_binds()
bound, kept = [], []
for scope, key, name, gesture in BINDS:
    if binds.get(scope, {}).get(key, {}).get(gesture):
        kept.append(f"{scope}/{key} {gesture}")
    else:
        model.set_bind(scope, key, name, gesture)
        bound.append(f"{scope}/{key} {gesture} -> {name}")

if model.get_schema_version() < model.SCHEMA_VERSION:
    model.set_schema_version(model.SCHEMA_VERSION)

print("INSTALL-ADDED:", ", ".join(added) or "nothing")
print("INSTALL-SKIPPED (already yours):", ", ".join(skipped) or "nothing")
print("INSTALL-BOUND:", "; ".join(bound) or "nothing")
print("INSTALL-KEPT (already bound):", "; ".join(kept) or "nothing")
