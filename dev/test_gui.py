"""End-to-end check inside a real FreeCAD GUI (offscreen).

Run by ``nix run .#e2e``: an isolated `freecad -M <repo>` executes this
script; once the GUI is up it drives the actual v2 addon -- startup path,
real command actions, the dispatcher installed on the application, the pie
widget, and the preferences dialog harvesting real icons -- then quits.
The wrapper greps the log for E2E-PASS / E2E-FAIL.
"""
import traceback

import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets


def check():
    ok = True
    try:
        from piemenu import dialog, model
        from piemenu import runtime as rt

        run = rt.runtime
        assert run is not None, "runtime did not start at GUI startup"
        assert model.get_schema_version() == 2, "migration did not run"
        assert run.pies, "no pies after startup"
        name = min(run.pies)
        print(f"E2E startup ok: pies={sorted(run.pies)}")

        # the pie is a registered command
        assert name in run._registered
        print("E2E command registration ok")

        # open a pie for real: visible widget, populated buttons
        widget = run.open_pie(name)
        assert widget is not None and widget.isVisible()
        buttons = [b for b in widget.buttons if not b.isHidden()]
        assert buttons, "pie opened with no buttons"
        icons = [b for b in buttons if not b.icon().isNull()]
        assert icons, "no real command icons resolved"
        widget.close()
        print(f"E2E pie widget ok: {len(buttons)} buttons, "
              f"{len(icons)} with real icons")

        # dispatch through the app: the starter bind is TAB (fresh config)
        key = next(iter(run._keys.values()), None)
        assert key is not None, "no shortcut bound"
        qt_key = QtGui.QKeySequence(key)[0]
        mw = Gui.getMainWindow()
        appinst = QtWidgets.QApplication.instance()

        def press():
            event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress,
                                    qt_key.key(), qt_key.keyboardModifiers())
            appinst.sendEvent(mw, event)

        press()
        assert run.dispatcher.current is not None \
            and run.dispatcher.current.isVisible(), "key did not open the pie"
        press()
        assert run.dispatcher.current is None \
            or not run.dispatcher.current.isVisible(), "toggle did not close"
        print(f"E2E dispatch ok: {key} opens and toggles")

        # the dialog against the real command population
        dlg = dialog.PieMenuPreferences(mw, on_change=run.reload)
        assert dlg.pie_list.count() >= 1
        assert len(dlg.actions) > 50, \
            f"only {len(dlg.actions)} commands harvested"
        assert dlg.slots.topLevelItemCount() == model.slot_count(dlg.pie())
        dlg.deleteLater()
        print(f"E2E dialog ok: {len(dlg.actions)} commands in the picker")

        # foreign-workbench icons resolve via the command registry, without
        # that workbench ever having been activated
        icon = rt.command_icon("Sketcher_ConstrainCoincident")
        assert icon is not None and not icon.isNull(), \
            "registry icon fallback failed"
        print("E2E registry icons ok")

        print("E2E-PASS")
    except Exception:  # noqa: BLE001 -- any failure must print E2E-FAIL
        traceback.print_exc()
        ok = False
        print("E2E-FAIL")
    finally:
        QtCore.QTimer.singleShot(
            300, QtWidgets.QApplication.instance().quit)
    return ok


# let the GUI finish coming up first
QtCore.QTimer.singleShot(2500, check)
