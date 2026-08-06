"""Copy appearance settings from the real FreeCAD profile into the scratch one.

Plain python, no FreeCAD: reads the real user.cfg strictly read-only and
grafts the appearance parameter groups (theme, stylesheet, colors) into the
scratch profile's user.cfg, so the dev instance looks like the real one
without ever writing to the real config.

    python3 dev/copy_theme.py [scratch-root]     # default /tmp/piemenu-dev
"""
import os
import sys
import xml.etree.ElementTree as ET

REAL = os.path.expanduser("~/.config/FreeCAD/v1-1/user.cfg")
# whole groups that are pure appearance
GROUPS = ("Themes", "View", "Bitmaps")
# from MainWindow, ONLY the theme keys: the whole group drags window state
# along. NOTE: Theme/StyleSheet hang FreeCAD under QT_QPA_PLATFORM=offscreen
# (the snap harness therefore uses its own theme-free scratch); on a real
# display they are fine.
MAINWINDOW_KEYS = ("Theme", "StyleSheet", "IconSet", "CursorTheme")


def find_group(parent, name):
    for child in parent.findall("FCParamGroup"):
        if child.get("Name") == name:
            return child
    return None


def descend(root, *names, create=False):
    node = root
    for name in names:
        nxt = find_group(node, name)
        if nxt is None:
            if not create:
                return None
            nxt = ET.SubElement(node, "FCParamGroup", {"Name": name})
        node = nxt
    return node


def main():
    scratch_root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/piemenu-dev"
    scratch = os.path.join(scratch_root, "config", "FreeCAD", "v1-1",
                           "user.cfg")
    if not os.path.exists(REAL):
        sys.exit(f"no real config at {REAL}")
    if not os.path.exists(scratch):
        sys.exit(f"no scratch config at {scratch} — launch once first")

    real_tree = ET.parse(REAL)
    real_prefs = descend(real_tree.getroot(), "Root", "BaseApp", "Preferences")
    if real_prefs is None:
        sys.exit("real config has no Preferences group")

    scratch_tree = ET.parse(scratch)
    scratch_prefs = descend(scratch_tree.getroot(), "Root", "BaseApp",
                            "Preferences", create=True)

    copied = []
    src_mw = find_group(real_prefs, "MainWindow")
    if src_mw is not None:
        old = find_group(scratch_prefs, "MainWindow")
        if old is not None:
            scratch_prefs.remove(old)
        dst_mw = ET.SubElement(scratch_prefs, "FCParamGroup",
                               {"Name": "MainWindow"})
        for child in list(src_mw):
            if child.tag != "FCParamGroup" \
                    and child.get("Name") in MAINWINDOW_KEYS:
                dst_mw.append(child)
        copied.append("MainWindow(theme keys)")
    for name in GROUPS:
        src = find_group(real_prefs, name)
        if src is None:
            continue
        old = find_group(scratch_prefs, name)
        if old is not None:
            scratch_prefs.remove(old)
        scratch_prefs.append(src)      # a copy of the subtree by reference
        copied.append(name)

    scratch_tree.write(scratch, encoding="utf-8", xml_declaration=True)
    print("THEME-COPIED:", ", ".join(copied))


if __name__ == "__main__":
    main()
