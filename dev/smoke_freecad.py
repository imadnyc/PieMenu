"""Headless smoke test: the v2 startup end to end under freecadcmd.

Seeds a legacy v1 tree in the isolated config, imports InitGui (with the
console-mode FreeCADGui shimmed), and asserts that the migration ran, the
runtime came up with the migrated pies, and the legacy shortcut resolves.
Run via ``nix run .#smoke``.
"""
# ruff: noqa: F401, I001  -- imports are deliberately interleaved with the
#   sys.path setup, and InitGui / FreeCADGui are imported for side effects.
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from PySide import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import FreeCAD as App
import FreeCADGui  # exists in console mode but half-empty

_mw = QtWidgets.QMainWindow()


class _GuiShim:  # auto-stub every missing GUI symbol
    def __getattr__(self, name):
        return MagicMock()

    def getMainWindow(self):
        return _mw


sys.modules["FreeCADGui"] = _GuiShim()

# a legacy tree that must migrate at startup (duplicate index on purpose)
root = App.ParamGet("User parameter:BaseApp/PieMenu")
root.RemGroup("V2")
index = App.ParamGet("User parameter:BaseApp/PieMenu/Index")
index.SetString("IndexList", "0.,.0")
index.SetString("0", "LegacyPie")
index.GetGroup("0").SetString("ToolList", "Std_New.,.Std_Save")
root.SetString("GlobalShortcutKey", "TAB")
root.SetString("CurrentPie", "LegacyPie")

import InitGui

from piemenu import model
from piemenu import runtime as rt

assert model.get_schema_version() == 2, model.get_schema_version()
pies = model.load_pies()
assert "LegacyPie" in pies, list(pies)
assert pies["LegacyPie"].items[0][0].cmd == "Std_New"
assert rt.runtime is not None, "runtime did not start"
assert "LegacyPie" in rt.runtime.pies
binds = model.load_binds()
assert model.resolve_key("TAB", "AnyWorkbenchAtAll", binds)[0] == "LegacyPie"

# a second start must be a no-op (the re-entrancy guard)
before = rt.runtime
InitGui.pieMenuStart()
assert rt.runtime is before

print("SMOKE-PASS: v2 startup — migration ran, runtime up, TAB resolves")
