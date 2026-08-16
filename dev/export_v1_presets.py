"""Translate a v1 PieMenu config into preset JSON files.

Reads a real user.cfg READ-ONLY, mirrors its v1 PieMenu parameters into
the (isolated) profile this runs under, runs the normal v1->v2 migration,
and writes every resulting pie as presets/<Name>.piemenu.json.

    env PRESET_SOURCE=~/.config/FreeCAD/v1-1/user.cfg \
        XDG_CONFIG_HOME=/tmp/scratch/... freecadcmd dev/export_v1_presets.py
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.environ.get("PIEMENU_REPO",
                                  "/home/dre/Projects/PieMenu"))

import FreeCAD as App

from piemenu import migrate, model

SOURCE = os.environ.get(
    "PRESET_SOURCE",
    os.path.expanduser("~/.config/FreeCAD/v1-1/user.cfg"))
OUT = os.environ.get(
    "PRESET_OUT",
    os.path.join(os.environ.get("PIEMENU_REPO",
                                "/home/dre/Projects/PieMenu"), "presets"))


def find(node, name):
    for child in node.findall("FCParamGroup"):
        if child.get("Name") == name:
            return child
    return None


def mirror(elem, grp):
    """Recreate one XML param group in the live parameter tree."""
    for e in elem:
        name = e.get("Name")
        if e.tag == "FCParamGroup":
            if name == "V2":
                continue             # only the v1 half matters here
            mirror(e, grp.GetGroup(name))
        elif e.tag == "FCText":
            grp.SetString(name, e.text or "")
        elif e.tag == "FCInt":
            grp.SetInt(name, int(e.get("Value", "0")))
        elif e.tag == "FCUInt":
            grp.SetUnsigned(name, int(e.get("Value", "0")))
        elif e.tag == "FCBool":
            grp.SetBool(name, e.get("Value", "0") in ("1", "true", "True"))
        elif e.tag == "FCFloat":
            grp.SetFloat(name, float(e.get("Value", "0")))


tree = ET.parse(SOURCE)
pm = find(find(find(tree.getroot(), "Root"), "BaseApp"), "PieMenu")
if pm is None:
    print("PRESETS-FAIL: no v1 PieMenu group in", SOURCE, flush=True)
    raise SystemExit(1)

App.ParamGet("User parameter:BaseApp").RemGroup("PieMenu")
mirror(pm, App.ParamGet("User parameter:BaseApp/PieMenu"))

migrate.migrate()
pies = model.load_pies()

os.makedirs(OUT, exist_ok=True)
for name, pie in sorted(pies.items()):
    data = {f: getattr(pie, f) for f in
            ("name", "family", "icon", "slots", "per_ring", "ring_mode",
             "ring_counts", "radius", "arc", "arc_face", "stagger",
             "stagger_by", "cols", "rows", "anchors", "anchor_offsets",
             "button", "spacing", "accent", "run_on", "delay",
             "alt_size", "door_hover")}
    data["items"] = [[{"cmd": b.cmd, "rule": model.encode_rule(b.rule),
                       "label": b.label}
                      for b in (slot or [])] for slot in pie.items]
    path = os.path.join(OUT, f"{name}.piemenu.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    filled = sum(1 for s in pie.items if s)
    print(f"PRESET: {name} -> {filled} filled slots", flush=True)
print("PRESETS-DONE", flush=True)
