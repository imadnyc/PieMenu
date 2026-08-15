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
# preferences).  This file only migrates, starts the runtime and registers
# the preferences page -- IMPLEMENTATION.md and UI-FEEDBACK.md are the
# design record.


def pieMenuStart():
    """Start PieMenu.  Guarded so a reload cannot double-install."""
    import FreeCAD as App
    import FreeCADGui as Gui

    from piemenu import dialog, migrate, resources, runtime

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

    # Edit > Preferences > PieMenu.  The group icon resolves by name
    # (preferences-piemenu.svg) through the registered icon path.
    try:
        Gui.addIconPath(resources.respath)
        Gui.addPreferencePage(dialog.PreferencePage, "PieMenu")
    except Exception as exc:  # noqa: BLE001 -- never block startup
        App.Console.PrintWarning(f"PieMenu: preferences page: {exc}\n")

    App.Console.PrintMessage("PieMenu v2 ready\n")


pieMenuStart()
