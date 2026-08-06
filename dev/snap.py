"""Photograph the addon's widgets for the styling loop.

Runs inside a real (offscreen) FreeCAD via ``nix run .#snap``.  Saves PNGs of
the live pie in several selection states and of the preferences dialog to
/tmp/piemenu-snaps/, then quits.  ``QWidget.grab()`` renders pixel-perfect
captures without needing a visible screen.
"""
import os
import traceback

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

OUT = "/tmp/piemenu-snaps"


def snap(widget, name):
    widget.grab().save(os.path.join(OUT, name + ".png"))
    print(f"SNAP {name}", flush=True)


def run():
    try:
        os.makedirs(OUT, exist_ok=True)
        from piemenu import dialog, model
        from piemenu import runtime as rt

        run_ = rt.runtime
        assert run_ is not None and run_.pies, "runtime not up"
        print("SNAP step: runtime up", flush=True)

        def fire(cmd):
            pass  # never actually run tools while photographing

        # the pie under different selections, straight from the real widget
        for label, counts in (("pie-main-noselection", {}),
                              ("pie-main-face", {"Face": 1}),
                              ("pie-main-edge", {"Edge": 1})):
            w = rt.PieWidget(run_.pies, "Main", counts, fire)
            w.popup_at(QtCore.QPoint(600, 400))
            snap(w, label)
            w.close()

        if "Modelling" in run_.pies:
            w = rt.PieWidget(run_.pies, "Modelling", {"Face": 2}, fire)
            w.popup_at(QtCore.QPoint(600, 400))
            for i, slot in enumerate(run_.pies["Modelling"].items):
                bindings = model.live_bindings(slot, {"Face": 2})
                if len(bindings) > 1:
                    w.show_chooser(w.buttons[i], bindings)
                    break
            snap(w, "pie-modelling-2faces-chooser")
            w.close()

            w = rt.PieWidget(run_.pies, "Modelling", {"Face": 2}, fire)
            w.popup_at(QtCore.QPoint(600, 400))
            w._aim = QtCore.QPoint(int(w._origin[0] + 70),
                                   int(w._origin[1] - 55))
            w.update()
            snap(w, "pie-modelling-gesture-arrow")
            w.close()

        print("SNAP step: pies done, building dialog", flush=True)
        dlg = dialog.PieMenuPreferences(Gui.getMainWindow(),
                                        on_change=run_.reload)
        dlg.resize(1280, 760)
        snap(dlg, "dialog-main")
        dlg.select_pie("Modelling")
        snap(dlg, "dialog-modelling")
        dlg.deleteLater()

        print("SNAP-DONE", flush=True)
    except Exception:  # noqa: BLE001 -- report and quit either way
        traceback.print_exc()
        print("SNAP-FAIL", flush=True)
    finally:
        QtCore.QTimer.singleShot(
            200, QtWidgets.QApplication.instance().quit)


QtCore.QTimer.singleShot(2500, run)
