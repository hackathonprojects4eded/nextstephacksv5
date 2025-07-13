import sys


def set_window_transparency(window, color="black", alpha=0.8):
    plat = sys.platform
    if plat.startswith("win"):
        window.wm_attributes("-transparentcolor", color)
    elif plat == "darwin":
        window.wm_attributes("-alpha", 1)
        window.wm_attributes("-transparent", True)
    else:
        window.wm_attributes("-alpha", alpha)
