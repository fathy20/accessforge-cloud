"""Headless stubs for tkinter / customtkinter so we can import redsea_toolkit
without a display server. Install BEFORE importing redsea_toolkit.

The original desktop file (redsea_toolkit.py) is preserved verbatim per user
request ("متغيرش في كود فيها"). The worker only calls the pure helper
functions (covering, TcmIndexer, build_check_regexes, TASK_PATTERN,
CHECK_RELATIONS, page_to_image, ocr_page_text, group_contiguous, …) — none
of which actually touch the GUI.
"""
import sys, types


def _noop(*_a, **_kw): return _Stub()


class _Stub:
    def __init__(self, *_a, **_kw): pass
    def __call__(self, *_a, **_kw): return _Stub()
    def __getattr__(self, _name): return _noop
    def __setattr__(self, _name, _value): pass
    def __getitem__(self, _k): return _Stub()
    def __setitem__(self, *_a, **_kw): pass
    def __iter__(self): return iter([])


def install() -> None:
    if "tkinter" in sys.modules:
        return
    tk = types.ModuleType("tkinter")
    tk.Tk = _Stub; tk.Toplevel = _Stub; tk.Frame = _Stub; tk.Label = _Stub
    tk.Button = _Stub; tk.Entry = _Stub; tk.Text = _Stub; tk.Canvas = _Stub
    tk.StringVar = _Stub; tk.IntVar = _Stub; tk.BooleanVar = _Stub
    tk.PhotoImage = _Stub; tk.TclError = Exception
    tk.NORMAL = "normal"; tk.DISABLED = "disabled"; tk.END = "end"
    tk.LEFT = "left"; tk.RIGHT = "right"; tk.TOP = "top"; tk.BOTTOM = "bottom"
    tk.BOTH = "both"; tk.X = "x"; tk.Y = "y"; tk.NONE = "none"
    tk.W = "w"; tk.E = "e"; tk.N = "n"; tk.S = "s"; tk.CENTER = "center"
    sys.modules["tkinter"] = tk

    for sub in ("filedialog", "messagebox", "ttk", "font", "scrolledtext"):
        m = types.ModuleType(f"tkinter.{sub}")
        m.__getattr__ = lambda _n: _noop  # type: ignore
        sys.modules[f"tkinter.{sub}"] = m
        setattr(tk, sub, m)

    ctk = types.ModuleType("customtkinter")

    class _CTk(_Stub):
        pass

    ctk.CTk = _CTk
    ctk.CTkFrame = _Stub; ctk.CTkLabel = _Stub; ctk.CTkButton = _Stub
    ctk.CTkEntry = _Stub; ctk.CTkTextbox = _Stub; ctk.CTkScrollableFrame = _Stub
    ctk.CTkComboBox = _Stub; ctk.CTkOptionMenu = _Stub; ctk.CTkCheckBox = _Stub
    ctk.CTkRadioButton = _Stub; ctk.CTkProgressBar = _Stub; ctk.CTkSlider = _Stub
    ctk.CTkTabview = _Stub; ctk.CTkSwitch = _Stub; ctk.CTkImage = _Stub
    ctk.CTkToplevel = _Stub; ctk.CTkFont = _noop; ctk.StringVar = _Stub
    ctk.IntVar = _Stub; ctk.BooleanVar = _Stub
    ctk.set_appearance_mode = _noop; ctk.set_default_color_theme = _noop
    ctk.set_widget_scaling = _noop; ctk.set_window_scaling = _noop
    sys.modules["customtkinter"] = ctk
