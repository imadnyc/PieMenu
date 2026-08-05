#!/usr/bin/env python3
"""Build the interactive preferences mockup.

    python3 mockups/build.py && xdg-open mockups/preferences.html

The addon's own SVGs in Resources/icons are inlined as markup rather than as
data URIs -- the browser would not render them from an <img src="data:...">.
Those 23 are interface chrome (add, remove, up, down, rename, copy, separator);
per-command icons such as Pad or Fillet live in FreeCAD's compiled resources,
not in this repository, so tools use drawn stand-ins.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def inline_icons():
    """Strip each SVG down to markup that can be dropped straight into innerHTML."""
    icons = {}
    src = os.path.join(REPO, "Resources", "icons")
    for name in sorted(os.listdir(src)):
        if not name.endswith(".svg"):
            continue
        body = open(os.path.join(src, name), encoding="utf-8", errors="replace").read()
        body = re.sub(r"<\?xml[^>]*\?>", "", body)
        body = re.sub(r"<!DOCTYPE[^>]*>", "", body)
        start = re.search(r"<svg\b", body)
        if start:
            body = body[start.start():]
        # let CSS size it: drop the fixed width/height, keep the viewBox
        body = re.sub(r'\s(width|height)="[^"]*"', "", body, count=2)
        # <metadata>/<title>/<desc> render as stray text inside a list row
        for tag in ("metadata", "title", "desc"):
            body = re.sub(r"<%s\b.*?</%s>" % (tag, tag), "", body, flags=re.S)
        icons[name[:-4]] = re.sub(r"\s+", " ", body).strip()
    return icons


DEMOED = {1,2,3,4,5,6,7,8,9,10,11,12,14,15,16,19,20,21,22,23,24,25}
DEFERRED = {17, 18}   # pinning: revisit once the model is settled
SUPERSEDES = {13: "F9.2 · bc3df9c", 17: "F8.c · b619aed", 18: "F8.c · b619aed",
              16: "F6.0 · 2b75adc", 19: "F3 · dded196", 22: "F10a · cb443f3"}


def plan_items():
    """Read UI-FEEDBACK.md so the sidebar cannot drift from the plan."""
    md = open(os.path.join(REPO, "UI-FEEDBACK.md"), encoding="utf-8").read()
    items = {}
    # table rows:  | 7 | Request | Notes |
    for n, title, note in re.findall(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$",
                                     md, re.M):
        items[int(n)] = {"title": title, "note": note}
    # prose entries:  **16. Consolidate ...**
    for n, title in re.findall(r"\*\*(\d+)\.\s*(.+?)\*\*", md):
        items.setdefault(int(n), {"title": title, "note": ""})
    out = []
    for n in sorted(items):
        it = items[n]
        clean = re.sub(r"[*`]", "", it["title"])
        clean = re.sub(r"\s+", " ", clean).strip()
        out.append({"n": n, "title": clean,
                    "note": re.sub(r"[*`]", "", it["note"])[:150],
                    "shown": n in DEMOED,
                    "deferred": n in DEFERRED,
                    "supersedes": "" if n in DEFERRED else SUPERSEDES.get(n, "")})
    return out


def main():
    icons = json.dumps(inline_icons())
    plan = json.dumps(plan_items())

    # preferences = the stable view; preferences2 = its evolving copy
    # (real six-axis rules, sub-pies as commands), kept side by side to compare.
    for name in ("preferences", "preferences2"):
        tpl = open(os.path.join(HERE, name + ".template.html"), encoding="utf-8").read()
        out = tpl.replace("__ICONS__", icons).replace("__PLAN__", plan)
        dest = os.path.join(HERE, name + ".html")
        open(dest, "w", encoding="utf-8").write(out)
        print("wrote", dest)

    # Single-question page kept as the shortcuts explainer.
    tpl = open(os.path.join(HERE, "shortcuts.template.html"), encoding="utf-8").read()
    dest = os.path.join(HERE, "shortcuts.html")
    open(dest, "w", encoding="utf-8").write(tpl.replace("__ICONS__", icons))
    print("wrote", dest)


if __name__ == "__main__":
    main()
