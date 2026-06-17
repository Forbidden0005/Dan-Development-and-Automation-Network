"""Dan GUI controller mixin — non-visual application logic shared by all GUI shells.

This module defines :class:`DanControllerMixin`, a mixin class that provides:

- Provider and tool initialisation (``_init_dan``)
- Keyboard shortcut binding (``_bind_shortcuts``, ``_cancel_if_processing``,
  ``_handle_enter``)
- Session loading (``load_session``)
- Shared stateless UI helpers (``_inline_error``, ``_clear_chat``,
  ``_scroll_to_bottom``)

Background
----------
``DanModernGUI`` (the supported desktop shell) previously inherited directly
from ``DanGUI`` (the legacy shell), which coupled the two shells and prevented
retiring the legacy code.  This mixin extracts the controller behaviour that
both shells legitimately share so that each shell can inherit from
``ctk.CTk`` + ``DanControllerMixin`` independently.

Usage::

    from gui_compat import ctk
    from dan_gui_controller import DanControllerMixin

    class MyShell(ctk.CTk, DanControllerMixin):
        def __init__(self):
            super().__init__()           # initialises ctk.CTk window
            self._init_controller_state()
            self._init_dan()             # register tools + init provider
            self._build_ui()
            self._bind_shortcuts()
            if not self._load_history():
                self.add_message("assistant", "Hello.")

        def _init_controller_state(self):
            import uuid, tkinter as tk
            from api_config import load_config
            from config import DEFAULT_PROVIDER, DEFAULT_MODEL
            self.messages = []
            self.provider = None
            self.is_processing = False
            self._session_id = str(uuid.uuid4())[:8]
            self._search_var = tk.StringVar()
            cfg = load_config()
            self.provider_name = cfg.get("provider") or DEFAULT_PROVIDER
            self.model_name = (
                cfg.get(self.provider_name, {}).get("model")
                or cfg.get("model")
                or DEFAULT_MODEL
            )

Interface contract
------------------
The host class **must** provide the following attributes and methods, all of
which are used by the mixin at runtime:

Attributes set by the host before mixin methods are called:
    messages              — list of conversation messages
    is_processing         — bool: True while a generation is running
    provider              — current provider object (or None)
    provider_name         — str: name of the active provider
    model_name            — str: name of the active model
    _session_id           — str: short session identifier
    messages_container    — CTkScrollableFrame holding message widgets

Methods provided by the host:
    add_message(role, content)  — render a message bubble into the chat area
    _finish_processing()        — reset UI state after generation ends
    _render_messages(messages)  — re-render a list of stored messages
    _update_tokens()            — update the token-count display
    refresh_sidebar()           — refresh the session history list
    send_message()              — trigger the AI generation flow
    new_chat()                  — clear chat and start a fresh session
    show_settings()             — open the settings dialog
    show_prompts()              — open the prompt library dialog
"""

from __future__ import annotations

import json
import logging
import uuid

from config import USER_DATA_DIR
from dan_gui_support import register_all_tools
from providers import get_provider
from workers import configure_worker_runner

logger = logging.getLogger("dan.gui.controller")


class DanControllerMixin:
    """Non-visual controller behaviour shared across Dan GUI shells.

    Designed for multiple inheritance alongside ``ctk.CTk``::

        class MyShell(ctk.CTk, DanControllerMixin): ...

    This mixin has no ``__init__``; the host is responsible for setting the
    instance variables documented in the module-level contract before calling
    any mixin methods.
    """

    # ------------------------------------------------------------------
    # Provider and tool initialisation
    # ------------------------------------------------------------------

    def _init_dan(self) -> None:
        """Register all tools and initialise the AI provider.

        Called once during shell ``__init__``.  Sets ``self.provider`` on
        success.  On failure, schedules an inline error via ``self.after`` so
        the window can still open and display the problem without a hard crash.
        """
        # Delegate to the canonical entry point shared by CLI and GUI.
        register_all_tools()
        configure_worker_runner(self._worker_runner)
        try:
            self.provider = get_provider(self.provider_name, self.model_name)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.after(
                500,
                lambda message=msg: self._inline_error(f"Provider init failed: {message}"),
            )

    def _worker_runner(self, prompt: str, worker_type: str, session_id: str) -> str:
        from agent import run_agent_loop

        provider = get_provider(self.provider_name, self.model_name)
        response, _ = run_agent_loop(prompt, [], provider)
        return response

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _bind_shortcuts(self) -> None:
        """Bind application-level keyboard shortcuts to the window.

        All targets (``new_chat``, ``show_settings``, ``show_prompts``,
        ``_cancel_if_processing``) are resolved at runtime via the normal
        Python MRO, so host-class overrides are respected automatically.
        """
        self.bind("<Control-n>", lambda e: self.new_chat())
        self.bind("<Control-l>", lambda e: self.new_chat())
        self.bind("<Control-comma>", lambda e: self.show_settings())
        self.bind("<Control-p>", lambda e: self.show_prompts())
        self.bind("<Escape>", lambda e: self._cancel_if_processing())

    def _cancel_if_processing(self) -> None:
        """Interrupt an in-progress generation when Escape is pressed.

        Displays an inline error message and resets the UI to idle.  Does
        nothing if no generation is running.
        """
        if self.is_processing:
            self._inline_error("Interrupted. Use /resume to continue.")
            self._finish_processing()

    def _handle_enter(self, event) -> str | None:
        """Key handler for the input box: send on Enter, newline on Shift+Enter.

        Returns ``"break"`` to suppress Tkinter's default newline insertion
        when the user presses plain Enter.
        """
        if not (event.state & 0x1):  # Shift bit is not set
            self.send_message()
            return "break"
        return None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def load_session(self, filename: str) -> None:
        """Load a saved session file into the current window.

        Reads ``USER_DATA_DIR/sessions/<filename>``, updates ``self.messages``
        and ``self._session_id``, clears the chat area, and re-renders stored
        messages.

        Does nothing if a generation is currently in progress.  Displays an
        inline error if the file cannot be read or parsed.
        """
        if self.is_processing:
            return
        try:
            fp = USER_DATA_DIR / "sessions" / filename
            data = json.loads(fp.read_text(encoding="utf-8"))
            self.messages = data.get("messages", [])
            self._session_id = data.get("session_id", str(uuid.uuid4())[:8])
            self._clear_chat()
            self._render_messages(self.messages)
            self._update_tokens()
            self.refresh_sidebar()
            self._scroll_to_bottom()
        except Exception as exc:  # noqa: BLE001
            self._inline_error(f"Could not load session: {exc}")

    # ------------------------------------------------------------------
    # Shared UI helpers
    # ------------------------------------------------------------------

    def _inline_error(self, msg: str) -> None:
        """Display *msg* as an inline error bubble in the chat area.

        Delegates to ``self.add_message`` so the host shell's error bubble
        style is used.
        """
        self.add_message("error", msg)

    def _clear_chat(self) -> None:
        """Destroy all child widgets inside ``self.messages_container``."""
        for widget in self.messages_container.winfo_children():
            widget.destroy()

    def _scroll_to_bottom(self) -> None:
        """Scroll ``self.messages_container`` to the bottom.

        Silently ignores errors — the canvas may not be ready or may have been
        destroyed during a theme rebuild.
        """
        try:
            self.messages_container._parent_canvas.yview_moveto(1.0)
        except Exception:  # noqa: BLE001
            pass
