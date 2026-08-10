"""The demo-GIF factory: script real widgets through an interaction,
grab every frame, let Pillow assemble looping GIFs into docs/gifs/.

Runs inside a real (offscreen) FreeCAD via ``nix run .#gifs`` so command
icons are the real ones. Each scene is a function that drives widgets
exactly the way the headless tests do (direct event calls), shooting
frames as it goes; a synthetic cursor is drawn onto the frames since
``QWidget.grab()`` has no pointer.
"""
import copy
import io
import os
import sys
import traceback

import FreeCADGui as Gui  # noqa: F401 -- GUI must be up for real icons
from PIL import Image, ImageDraw
from PySide import QtCore, QtGui, QtWidgets

REPO = os.environ.get("PIEMENU_REPO", "/home/dre/Projects/PieMenu")
sys.path.insert(0, os.path.join(REPO, "dev"))

import dark_shot  # lives in dev/, needs the path above

OUT = os.path.join(REPO, "docs", "gifs")
CANVAS = (360, 320)
BG = dark_shot.BG
CAPTION = (165, 165, 165)         # reads against the dark backdrop
FPS_MS = 90


def wait(ms):
    end = QtCore.QDateTime.currentMSecsSinceEpoch() + ms
    app = QtWidgets.QApplication.instance()
    while QtCore.QDateTime.currentMSecsSinceEpoch() < end:
        app.processEvents()


class Recorder:
    def __init__(self, size=CANVAS):
        self.size = size
        self.frames = []
        self.durations = []

    def shoot(self, widget, cursor=None, hold=1, caption=""):
        """One frame: the widget centred on the canvas, cursor drawn at
        widget-local coords, held for `hold` ticks."""
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        widget.grab().save(buffer, "PNG")
        shot = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")
        canvas = Image.new("RGB", self.size, BG)
        off = ((self.size[0] - shot.width) // 2,
               (self.size[1] - shot.height) // 2)
        canvas.paste(shot, off, shot)
        draw = ImageDraw.Draw(canvas)
        if cursor is not None:
            x = off[0] + int(cursor.x())
            y = off[1] + int(cursor.y())
            draw.polygon([(x, y), (x + 11, y + 4), (x + 4, y + 11)],
                         fill=(240, 240, 240), outline=(20, 20, 20))
        if caption:
            draw.text((8, self.size[1] - 16), caption, fill=CAPTION)
        self.frames.append(canvas.convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=128))
        self.durations.append(FPS_MS * hold)

    def blank(self, hold=4, caption=""):
        canvas = Image.new("RGB", self.size, BG)
        if caption:
            ImageDraw.Draw(canvas).text((8, self.size[1] - 16), caption,
                                        fill=CAPTION)
        self.frames.append(canvas.convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=128))
        self.durations.append(FPS_MS * hold)

    def save(self, name):
        path = os.path.join(OUT, name + ".gif")
        self.frames[0].save(
            path, save_all=True, append_images=self.frames[1:],
            duration=self.durations, loop=0, optimize=True)
        print(f"GIF {name} ({len(self.frames)} frames, "
              f"{os.path.getsize(path) // 1024} KB)", flush=True)


def move(widget, point):
    """A real mouse-move through the widget's handler, like the tests."""
    widget.mouseMoveEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove, QtCore.QPointF(point),
        QtCore.QPointF(widget.mapToGlobal(point)), QtCore.Qt.NoButton,
        QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
    QtWidgets.QApplication.instance().processEvents()


def glide(rec, widget, start, end, steps=8, hold_last=1):
    for i in range(1, steps + 1):
        t = i / steps
        point = QtCore.QPoint(
            int(start.x() + (end.x() - start.x()) * t),
            int(start.y() + (end.y() - start.y()) * t))
        move(widget, point)
        rec.shoot(widget, point, hold=hold_last if i == steps else 1)
    return point


def origin_of(widget):
    return QtCore.QPoint(int(widget._origin[0]), int(widget._origin[1]))


def button_centre(widget, index):
    button = widget.buttons[index]
    return button.geometry().center()


def fresh(rt, name, counts, run_on=None, delay=None):
    pies = {k: copy.deepcopy(v) for k, v in rt.runtime.pies.items()}
    if run_on:
        pies[name].run_on = run_on
    if delay is not None:
        pies[name].delay = delay
    widget = rt.PieWidget(pies, name, counts, lambda cmd: None)
    widget.popup_at(QtCore.QPoint(700, 500))
    return widget


# ---- the scenes ------------------------------------------------------------

def scene_gesture_aim(rt):
    """Hold, aim across sectors (highlight + centre readout), release."""
    rec = Recorder()
    widget = fresh(rt, "Main", {"Face": 1}, run_on="release")
    centre = origin_of(widget)
    rec.shoot(widget, centre, hold=4)
    slot1 = button_centre(widget, 1)
    at = glide(rec, widget, centre, slot1, hold_last=6)
    slot2 = button_centre(widget, 2)
    at = glide(rec, widget, at, slot2, hold_last=6)
    widget.commit_gesture(pos=widget.mapToGlobal(at))   # release: fires
    rec.blank(hold=5)
    widget.close()
    rec.save("gesture-aim")


def scene_conditional_slots(rt):
    """The same pie under three selections: slots resolve differently."""
    rec = Recorder()
    for counts, caption in (({}, "nothing selected"),
                            ({"Face": 1}, "a face selected"),
                            ({"Edge": 1}, "an edge selected")):
        widget = fresh(rt, "Main", counts)
        rec.shoot(widget, None, hold=12, caption=caption)
        widget.close()
    rec.save("conditional-slots")


def scene_chooser(rt):
    """An overloaded slot pops its flavours; release over one picks it."""
    from piemenu import model
    rec = Recorder()
    widget = fresh(rt, "Modelling", {"Face": 2}, run_on="release")
    centre = origin_of(widget)
    rec.shoot(widget, centre, hold=4)
    target = None
    for i, slot in enumerate(widget.pie.items):
        bindings = model.live_bindings(slot, {"Face": 2})
        if len(bindings) > 1:
            target = (i, bindings)
            break
    index, bindings = target
    at = glide(rec, widget, centre, button_centre(widget, index),
               hold_last=4)
    widget.show_chooser(widget.buttons[index], bindings)
    wait(30)
    rec.shoot(widget, at, hold=6)
    alts = widget._chooser.findChildren(QtWidgets.QToolButton)
    for alt in alts:
        spot = widget._chooser.mapTo(widget, alt.geometry().center())
        rec.shoot(widget, spot, hold=4)
    rec.blank(hold=4)
    widget.close()
    rec.save("chooser")


def scene_door_dwell(rt):
    """Dwelling on a door slot glides into the sub-pie; ◂ goes back."""
    rec = Recorder()
    widget = fresh(rt, "Main", {}, run_on="release", delay=600)
    centre = origin_of(widget)
    rec.shoot(widget, centre, hold=4)
    door = next(i for i, slot in enumerate(widget.pie.items)
                if slot and slot[0].cmd.startswith("PieMenu_"))
    at = glide(rec, widget, centre, button_centre(widget, door),
               hold_last=2)
    app = QtWidgets.QApplication.instance()
    app.sendEvent(widget.buttons[door],
                  QtCore.QEvent(QtCore.QEvent.Enter))
    for _ in range(30):                    # the dwell ring fills
        wait(45)
        rec.shoot(widget, at)
        if widget.pie.name != "Main":
            break
    rec.shoot(widget, origin_of(widget), hold=10)   # inside the sub-pie
    widget.back()
    wait(30)
    rec.shoot(widget, origin_of(widget), hold=6)
    widget.close()
    rec.save("door-dwell")


def scene_dead_slot(rt):
    """Aiming at a greyed-out slot: named as unavailable, fires nothing."""
    rec = Recorder()
    widget = fresh(rt, "Modelling", {"Face": 1}, run_on="release")
    dead = next(i for i, b in enumerate(widget.buttons)
                if not b.isHidden() and not b.isEnabled())
    centre = origin_of(widget)
    rec.shoot(widget, centre, hold=4)
    at = glide(rec, widget, centre, button_centre(widget, dead),
               hold_last=10)
    widget.commit_gesture(pos=widget.mapToGlobal(at))   # runs nothing
    rec.blank(hold=5, caption="release: nothing runs")
    widget.close()
    rec.save("dead-slot")


def scene_pinned_palette(rt):
    """Pin a pie, drag it, snap it to the edge, tuck away, hover back."""
    host = QtWidgets.QWidget()
    host.setFixedSize(*CANVAS)
    host.setStyleSheet(f"background: rgb{BG};")
    host.show()
    rec = Recorder()
    widget = rt.PieWidget(rt.runtime.pies, "Booleans", {"Object": 2},
                          lambda cmd: None, parent=host, pinned=True)
    widget.move(90, 60)
    widget.show()
    widget.raise_()
    wait(30)

    def shoot_host(cursor=None, hold=1, caption=""):
        rec.shoot(host, cursor, hold=hold, caption=caption)

    grip = widget.geometry().center()
    shoot_host(grip, hold=6, caption="P pins the pie")
    for step in range(1, 7):               # drag toward the left edge
        pos = QtCore.QPoint(90 - step * 15, 60 + step * 4)
        widget.move(pos)
        wait(15)
        shoot_host(widget.geometry().center(), caption="drag anywhere")
    widget._snap_to_edge()
    wait(15)
    shoot_host(widget.geometry().center(), hold=6,
               caption="near the edge: snaps flush")
    widget._collapse()
    wait(15)
    shoot_host(None, hold=8, caption="mouse leaves: tucks away")
    widget._expand()
    wait(30)
    shoot_host(widget.geometry().center(), hold=8, caption="hover: back")
    widget.close()
    host.close()
    rec.save("pinned-palette")


def run():
    try:
        os.makedirs(OUT, exist_ok=True)
        from piemenu import runtime as rt
        assert rt.runtime is not None and rt.runtime.pies, "runtime not up"
        dark_shot.apply()
        for scene in (scene_gesture_aim, scene_conditional_slots,
                      scene_chooser, scene_door_dwell, scene_dead_slot,
                      scene_pinned_palette):
            scene(rt)
        print("GIFS-DONE", flush=True)
    except Exception:  # noqa: BLE001 -- the wrapper greps the sentinel
        traceback.print_exc()
        print("GIFS-FAIL", flush=True)
    finally:
        QtCore.QTimer.singleShot(
            300, QtWidgets.QApplication.instance().quit)


QtCore.QTimer.singleShot(2500, run)
