"""Paint the offscreen FreeCAD dark, for the README captures.

The doc images are shot in dark mode: this flips PieMenu's own Theme param
and hands Qt a matching palette, so the pies, the chooser and the whole
preferences dialog come out looking like a dark FreeCAD. Loading a real
theme stylesheet would do it too, but Theme/StyleSheet hang FreeCAD under
QT_QPA_PLATFORM=offscreen (see copy_theme.py); a palette doesn't.

Imported by snap.py and gif_scenes.py, both of which run inside a real
(offscreen) FreeCAD.
"""
from PySide import QtGui, QtWidgets

# what captures are composited on, so a shot is dark whatever page it lands
# on: THEMES["dark"] window, as RGB
BG = (45, 45, 45)


def apply():
    import FreeCAD as App

    from piemenu import runtime as rt

    app = QtWidgets.QApplication.instance()
    App.ParamGet(rt.MAIN).SetString("Theme", "dark")
    spec = rt.THEMES["dark"]
    window = QtGui.QColor(spec["window"])
    button = QtGui.QColor(spec["fill"])
    text = QtGui.QColor(spec["text"])
    mid = QtGui.QColor(spec["outline"])
    role = QtGui.QPalette
    pal = QtGui.QPalette()
    for which, color in ((role.Window, window), (role.Base, window.darker(125)),
                         (role.AlternateBase, button), (role.Button, button),
                         (role.ToolTipBase, button), (role.ToolTipText, text),
                         (role.Light, button.lighter(120)), (role.Mid, mid),
                         (role.Dark, mid.darker(130)), (role.Text, text),
                         (role.WindowText, text), (role.ButtonText, text),
                         (role.PlaceholderText, QtGui.QColor("#8a8a8a")),
                         (role.BrightText, QtGui.QColor("#ffffff"))):
        pal.setColor(which, color)
    for which in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(role.Disabled, which, QtGui.QColor("#8a8a8a"))
    # FreeCAD paints through a ~70 KB light stylesheet that outranks any
    # palette, and it has no dark sibling bundled — so drop it and let plain
    # Fusion (which does honor palettes) carry the dark colors. setStyle
    # resets the palette, hence the order.
    app.setStyleSheet("")
    app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    app.setPalette(pal)
    print(f"DARK-SHOT: theme dark, style={app.style().objectName()}, "
          f"win={app.palette().window().color().name()}", flush=True)
