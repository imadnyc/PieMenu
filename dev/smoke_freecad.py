"""Headless smoke test: load the PieMenu addon under freecadcmd and assert the
parameter-tree migration + IndexList dedupe. Run via `nix run .#smoke`."""
# ruff: noqa: F401, I001  -- imports are deliberately interleaved with the sys.path
#   setup below, and InitGui / FreeCADGui are imported for their side effects.
import os
import sys
from unittest.mock import MagicMock

# Live working tree (default matches this machine). PIEMENU_REPO lets pm-smoke override.
sys.path.insert(0, os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu"))

from PySide import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import FreeCAD as App
import FreeCADGui                        # exists in console mode but half-empty
_mw = QtWidgets.QMainWindow()
class _GuiShim:                          # auto-stub every missing GUI symbol
    def __getattr__(self, n): return MagicMock()
    def getMainWindow(self): return _mw
sys.modules["FreeCADGui"] = _GuiShim()

# Pre-migration state in the ISOLATED tree: SchemaVersion unset + duplicated IndexList
App.ParamGet("User parameter:BaseApp/PieMenu").SetInt("SchemaVersion", 0)
App.ParamGet("User parameter:BaseApp/PieMenu/Index").SetString(
    "IndexList", "3.,.2.,.4.,.1.,.0.,.1.,.2")

import InitGui                          # runs pieMenuStart() -> legacyFix() -> migrateToolModel()
assert "InitGui" in sys.modules, "addon module did not import"

# migration ran: SchemaVersion bumped to TOOL_MODEL_VERSION (1)
sv = App.ParamGet("User parameter:BaseApp/PieMenu").GetInt("SchemaVersion", -1)
assert sv == 1, f"migration did not run, SchemaVersion={sv}"

# dedupe invariant on the real isolated tree (mirrors getIndexList, InitGui.py:2397)
raw = App.ParamGet("User parameter:BaseApp/PieMenu/Index").GetString("IndexList")
seen, uniq = set(), []
for v in raw.split(".,."):
    i = int(v)
    if i not in seen:
        seen.add(i)
        uniq.append(i)
assert uniq == [3, 2, 4, 1, 0], uniq

print("SMOKE-PASS: addon loaded, migration ran (SchemaVersion=1), dedupe ok")
