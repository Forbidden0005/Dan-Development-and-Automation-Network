"""Compatibility helpers for optional CustomTkinter GUI runtime."""

from __future__ import annotations

from types import SimpleNamespace

CUSTOMTKINTER_AVAILABLE = False
CUSTOMTKINTER_IMPORT_ERROR: Exception | None = None

try:
    import customtkinter as ctk  # type: ignore[import-not-found]

    CUSTOMTKINTER_AVAILABLE = True
except ModuleNotFoundError as exc:
    CUSTOMTKINTER_IMPORT_ERROR = exc

    class _MissingWidget:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __getattr__(self, _name):
            def _noop(*args, **kwargs):
                return None

            return _noop

    class _MissingCanvas(_MissingWidget):
        pass

    def _noop(*args, **kwargs):
        return None

    ctk = SimpleNamespace(
        CTk=_MissingWidget,
        CTkFrame=_MissingWidget,
        CTkLabel=_MissingWidget,
        CTkButton=_MissingWidget,
        CTkTextbox=_MissingWidget,
        CTkEntry=_MissingWidget,
        CTkOptionMenu=_MissingWidget,
        CTkScrollableFrame=_MissingWidget,
        CTkToplevel=_MissingWidget,
        CTkCanvas=_MissingCanvas,
        CTkFont=_MissingWidget,
        set_appearance_mode=_noop,
        set_default_color_theme=_noop,
    )


def gui_dependency_message() -> str:
    """Return a user-facing message for missing GUI dependencies."""
    if CUSTOMTKINTER_AVAILABLE:
        return ""

    missing_name = "customtkinter"
    if isinstance(CUSTOMTKINTER_IMPORT_ERROR, ModuleNotFoundError):
        missing_name = CUSTOMTKINTER_IMPORT_ERROR.name or missing_name

    return (
        "Dan GUI cannot start because required GUI dependencies are missing.\n"
        f"Missing package: {missing_name}\n"
        "Install the runtime dependencies with:\n"
        "  py -m pip install -r requirements-core.txt"
    )


def ensure_gui_runtime() -> None:
    """Raise a clear runtime error if GUI dependencies are unavailable."""
    if CUSTOMTKINTER_AVAILABLE:
        return
    raise RuntimeError(gui_dependency_message())
