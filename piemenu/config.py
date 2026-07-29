PARAM_PATH       = "User parameter:BaseApp/PieMenu"
PARAM_INDEX_PATH = "User parameter:BaseApp/PieMenu/Index"
PARAM_ACCENTS    = "User parameter:BaseApp/Preferences/Themes"
PARAM_COLOR      = "User parameter:BaseApp/Preferences/View"

_params_cache = None

def get_params():
    global _params_cache
    if _params_cache is None:
        import FreeCAD as App
        _params_cache = {
            "main":    App.ParamGet(PARAM_PATH),
            "index":   App.ParamGet(PARAM_INDEX_PATH),
            "accents": App.ParamGet(PARAM_ACCENTS),
            "color":   App.ParamGet(PARAM_COLOR),
        }
    return _params_cache


def get_loaded_workbenches():
    import FreeCAD as App
    paramLoadedWb = "User parameter:BaseApp/Preferences/General"
    paramWb = App.ParamGet(paramLoadedWb)
    return paramWb.GetString("BackgroundAutoloadModules").split(",")
