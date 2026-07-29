from dataclasses import dataclass, field


@dataclass
class AppState:
    context_all: dict = field(default_factory=dict)

    shortcut_key: str = ""
    global_shortcut_key: str = "TAB"
    hover_delay: int = 100
    flag_shortcut_override: bool = False
    first_load: bool = True

    # # simple collections
    list_commands: list = field(default_factory=list)
    list_shortcut_code: list = field(default_factory=list)
    row_subgroup_map: dict[int, str] = field(default_factory=dict)
    sub_group_selected: str | None = None

    # # last pointer position from the event stream (global QtCore.QPoint)
    # # or None; Wayland forbids QCursor.pos() polling, but events still
    # # carry coords. Kept Qt-free here to avoid a PySide import in state.py.
    last_mouse_pos: object | None = None

app_state = AppState()

