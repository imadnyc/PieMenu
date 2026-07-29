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
        icons[name[:-4]] = re.sub(r"\s+", " ", body).strip()
    return icons


def main():
    tpl = open(os.path.join(HERE, "preferences.template.html"), encoding="utf-8").read()
    out = tpl.replace("__ICONS__", json.dumps(inline_icons()))
    dest = os.path.join(HERE, "preferences.html")
    open(dest, "w", encoding="utf-8").write(out)
    print("wrote", dest)


if __name__ == "__main__":
    main()
