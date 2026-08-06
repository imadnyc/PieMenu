# PieMenu widget for FreeCAD -- v2 bootstrap

# Copyright (C) 2026 Ben-PH,
# Copyright (C) 2024 Grubuntu, Pgilfernandez, hasecilu @ FreeCAD
# Copyright (C) 2022, 2023 mdkus @ FreeCAD
# Copyright (C) 2016, 2017 triplus @ FreeCAD
# Copyright (C) 2015,2016 looo @ FreeCAD
# Copyright (C) 2015 microelly <microelly2@freecadbuch.de>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# FreeCAD executes this file at GUI startup for every directory under Mod/.
# Everything real lives in the piemenu package: model (the data), migrate
# (v1 -> v2, run once), runtime (live pies and dispatch), dialog (the
# preferences).  This file only migrates, starts the runtime and adds the
# menu entry -- IMPLEMENTATION.md and UI-FEEDBACK.md are the design record.


def pieMenuStart():
    """Start PieMenu.  Guarded so a reload cannot double-install."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore

    from piemenu import dialog, migrate, runtime

    if runtime.runtime is not None:
        return

    try:
        migrate.migrate()
    except Exception as exc:  # noqa: BLE001 -- never block startup
        App.Console.PrintWarning(f"PieMenu: migration failed: {exc}\n")

    rt = runtime.start(Gui)

    def open_prefs():
        dialog.open_preferences(Gui.getMainWindow(), on_change=rt.reload)

    rt.open_preferences = open_prefs

    def add_menu_entry():
        """A Tools > Accessories entry, created if the submenu is absent.

        FreeCAD rebuilds the menu bar whenever a workbench activates, which
        destroys custom entries -- so this runs on a repeating timer and
        re-adds itself when it finds the action gone (the v1 approach).
        """
        from PySide import QtGui
        mw = Gui.getMainWindow()
        if mw is None:
            return
        if mw.findChild(QtGui.QAction, "PieMenuPreferencesAction") is not None:
            return
        tools = None
        for menu_action in mw.menuBar().actions():
            if menu_action.text().replace("&", "") == "Tools":
                tools = menu_action.menu()
                break
        if tools is None:
            return
        accessories = None
        for sub in tools.actions():
            if sub.text().replace("&", "") == "Accessories" and sub.menu():
                accessories = sub.menu()
                break
        if accessories is None:
            from PySide import QtWidgets
            accessories = QtWidgets.QMenu("Accessories", tools)
            tools.insertMenu(tools.actions()[0] if tools.actions() else None,
                             accessories)
        action = accessories.addAction("PieMenu preferences…")
        action.setObjectName("PieMenuPreferencesAction")
        action.triggered.connect(open_prefs)

    menu_timer = QtCore.QTimer()
    menu_timer.timeout.connect(add_menu_entry)
    menu_timer.start(1500)
    rt._menu_timer = menu_timer      # keep the timer alive
    App.Console.PrintMessage("PieMenu v2 ready\n")


pieMenuStart()
