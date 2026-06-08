#!/usr/bin/env python3
"""Claude-inspired modern shell for the Dan desktop GUI."""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
import uuid
from pathlib import Path

from actions import get_all_actions
from agent import AgentInterrupted, run_agent_loop
from config import APP_NAME, APP_VERSION, DEFAULT_MODEL, DEFAULT_PROVIDER, USER_DATA_DIR
from dan_gui_controller import DanControllerMixin
from dan_gui_support import (
    DEFAULT_PROMPT_TEMPLATE,
    build_actions_text,
    estimate_tokens,
    extract_assistant_text,
    format_relative_date,
    infer_provider_from_model,
    sanitize_prompt_name,
    session_title_from_file,
    timestamp_label,
)
from dan_gui_theme import THEME_DARK, THEME_LIGHT, get_theme_tokens, normalize_theme, theme_from_config
from gui_compat import ctk, ensure_gui_runtime
from providers import get_provider
from tool_registry import get_all_tools
import session_mgr


MODEL_CHOICES = [
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:32b",
    "llama3.1:8b",
    "deepseek-coder-v2:16b",
    "claude-sonnet-4-6",
    "claude-opus-4-20250514",
    "gpt-4o",
    "gpt-4o-mini",
]


class ModernLiveBubble:
    """Streaming assistant bubble using the active modern theme."""

    def __init__(self, parent, tokens, font_factory):
        self.ui = tokens
        self._font = font_factory
        self._has_content = False
        self._streaming = False
        self._full_text = ""

        self.outer = ctk.CTkFrame(parent, fg_color="transparent")
        self.outer.grid(sticky="ew", pady=(0, 10))
        self.outer.grid_columnconfigure(1, weight=1)
        self.outer.grid_columnconfigure(2, minsize=84, weight=0)

        avatar = ctk.CTkFrame(
            self.outer,
            width=32,
            height=32,
            fg_color=self.ui.accent_soft,
            corner_radius=16,
            border_width=1,
            border_color=self.ui.border,
        )
        avatar.grid(row=0, column=0, padx=(0, 10), sticky="n", pady=(4, 0))
        avatar.grid_propagate(False)
        ctk.CTkLabel(
            avatar,
            text="D",
            width=32,
            height=32,
            font=self._font(14, "bold"),
            text_color=self.ui.accent,
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.bubble = ctk.CTkFrame(
            self.outer,
            fg_color=self.ui.assistant_bubble,
            corner_radius=16,
            border_width=1,
            border_color=self.ui.border,
        )
        self.bubble.grid(row=0, column=1, sticky="ew")
        self.bubble.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(
            self.bubble,
            text="Working...",
            anchor="w",
            font=self._font(12),
            text_color=self.ui.text_subtle,
        )
        self.status.grid(row=0, column=0, padx=14, pady=12, sticky="w")

        self.textbox = ctk.CTkTextbox(
            self.bubble,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            wrap="word",
            height=42,
            font=self._font(14),
            text_color=self.ui.text,
            activate_scrollbars=False,
        )
        self._textbox_widget = self.textbox._textbox
        self._textbox_widget.tag_configure("tool", foreground=self.ui.tool_text)
        self._textbox_widget.tag_configure("normal", foreground=self.ui.text)

    def set_status(self, _=None):
        return None

    def add_tool_line(self, text: str):
        self._ensure_textbox()
        self.textbox.configure(state="normal")
        self._textbox_widget.insert("end", text + "\n", "tool")
        self._fit()
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def append_text(self, chunk: str):
        self._ensure_textbox()
        self._full_text += chunk
        if not self._streaming:
            self._streaming = True
            if self._has_content:
                self.textbox.configure(state="normal")
                self._textbox_widget.insert("end", "\n", "normal")
                self.textbox.configure(state="disabled")
        self.textbox.configure(state="normal")
        self._textbox_widget.insert("end", chunk, "normal")
        self._fit()
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def finish(self, fallback: str = ""):
        if not self._has_content and fallback:
            self._ensure_textbox()
            self._full_text = fallback
            self.textbox.configure(state="normal")
            self._textbox_widget.insert("end", fallback, "normal")
            self.textbox.configure(state="disabled")
        self._fit()
        self._add_copy_button()

    def _ensure_textbox(self):
        if self._has_content:
            return
        self._has_content = True
        try:
            self.status.grid_remove()
        except Exception:
            pass
        self.textbox.grid(row=0, column=0, sticky="ew", padx=6, pady=8)

    def _fit(self):
        try:
            lines = int(self.textbox.index("end-1c").split(".")[0])
            self.textbox.configure(height=min(max(lines * 22 + 16, 50), 700))
        except Exception:
            pass

    def _add_copy_button(self):
        try:
            text_value = self._full_text.strip() or self.textbox.get("1.0", "end-1c").strip()
            if not text_value:
                return
            copy_button = ctk.CTkButton(
                self.bubble,
                text="Copy",
                width=48,
                height=24,
                fg_color="transparent",
                hover_color=self.ui.surface_hover,
                text_color=self.ui.text_subtle,
                corner_radius=8,
                font=self._font(11),
                command=lambda value=text_value: (
                    self.bubble.winfo_toplevel().clipboard_clear(),
                    self.bubble.winfo_toplevel().clipboard_append(value),
                ),
            )
            copy_button.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)
            copy_button.lower()
            self.bubble.bind("<Enter>", lambda _event: copy_button.lift())
            self.bubble.bind("<Leave>", lambda _event: copy_button.lower())
        except Exception:
            pass


class DanModernGUI(ctk.CTk, DanControllerMixin):
    """Supported desktop shell: Claude-inspired, Dan-branded, theme-aware.

    Inherits window behaviour from ``ctk.CTk`` and non-visual controller
    behaviour (tool init, shortcut binding, session loading) from
    ``DanControllerMixin``.  The legacy ``DanGUI`` class is no longer in the
    inheritance chain — this shell is fully self-contained.
    """

    SIDEBAR_W = 304
    RIGHT_RAIL_W = 264

    def __init__(self):
        from api_config import load_config

        # Load config once; reuse for both theme and provider initialisation.
        cfg = load_config()
        self._theme_name = theme_from_config(cfg)
        self.ui = get_theme_tokens(self._theme_name)
        self._workspace_pane = "Files"
        self._workspace_buttons = {}

        # Initialise the ctk.CTk window base (the only __init__ in the chain).
        super().__init__()
        self.title(f"{APP_NAME} - v{APP_VERSION}")
        self.geometry("1180x660")
        self.minsize(1020, 600)

        # Controller state — previously delegated to DanGUI.__init__.
        self.messages: list = []
        self.provider = None
        self.is_processing = False
        self._session_id = str(uuid.uuid4())[:8]
        self._search_var = tk.StringVar()
        self.provider_name: str = cfg.get("provider") or DEFAULT_PROVIDER
        _pc = cfg.get(self.provider_name, {})
        self.model_name: str = (
            _pc.get("model") or cfg.get("model") or DEFAULT_MODEL
        )

        # Initialise tools + provider (DanControllerMixin._init_dan).
        self._init_dan()
        # Build the modern UI.
        self._build_ui()
        # Bind Ctrl+N, Ctrl+,, Ctrl+P, Escape (DanControllerMixin._bind_shortcuts).
        self._bind_shortcuts()
        # Restore the most recent auto-saved session, or show a welcome message.
        if not self._load_history():
            self.add_message(
                "assistant",
                f"Hey. I'm {APP_NAME}, your local-first development assistant.\n"
                "Ask me to inspect code, plan a change, debug a workflow, or build something.",
            )

    def _font(self, size: int, weight: str = "normal"):
        return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)

    def _label(self, parent, text, size=13, weight="normal", color=None, **kwargs):
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=color or self.ui.text,
            font=self._font(size, weight),
            **kwargs,
        )

    def _button(
        self,
        parent,
        text,
        command,
        *,
        width=None,
        height=36,
        fg_color=None,
        hover_color=None,
        text_color=None,
        radius=10,
        border=False,
        **kwargs,
    ):
        props = {
            "height": height,
            "fg_color": fg_color or self.ui.surface,
            "hover_color": hover_color or self.ui.surface_hover,
            "text_color": text_color or self.ui.text,
            "corner_radius": radius,
            "font": self._font(13),
            "command": command,
        }
        if border:
            props.update({"border_width": 1, "border_color": self.ui.border})
        if width is not None:
            props["width"] = width
        props.update(kwargs)
        return ctk.CTkButton(parent, text=text, **props)

    def _popup(self, title: str, width: int, height: int):
        window = ctk.CTkToplevel(self)
        window.title(title)
        window.geometry(f"{width}x{height}")
        window.configure(fg_color=self.ui.background)
        window.transient(self)
        window.grab_set()
        window.after(50, lambda: (window.lift(), window.focus_force()))
        return window

    def _shell_counts(self) -> tuple[int, int]:
        return len(session_mgr.list_sessions(include_auto=True)), len(get_all_tools())

    def _build_ui(self):
        ctk.set_appearance_mode(self.ui.appearance_mode)
        self.configure(fg_color=self.ui.background)
        self.grid_columnconfigure(0, weight=0, minsize=self.SIDEBAR_W)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=self.RIGHT_RAIL_W)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self._build_sidebar()
        self._build_header()
        self._build_chat_area()
        self._build_right_rail()
        self._build_status_bar()

    def _build_header(self):
        header = ctk.CTkFrame(self, height=64, fg_color=self.ui.main, corner_radius=0)
        header.grid(row=0, column=1, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=0, padx=24, pady=12, sticky="w")
        self._label(title, "What do you want to build?", 18, "bold").grid(
            row=0, column=0, sticky="w"
        )
        self._label(
            title,
            "Chat-first local workspace.",
            11,
            color=self.ui.text_subtle,
        ).grid(row=1, column=0, sticky="w")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=1, padx=(8, 20), pady=12, sticky="e")

        self._model_lbl = self._label(
            controls,
            f"  {self.model_name}  ",
            11,
            color=self.ui.text_muted,
        )
        self._model_lbl.grid(row=0, column=0, padx=(0, 8))

        self._provider_lbl = self._label(
            controls,
            f"  {self.provider_name}  ",
            11,
            color=self.ui.text_subtle,
        )
        self._provider_lbl.grid(row=0, column=1, padx=(0, 8))

        target_theme = THEME_LIGHT if self._theme_name == THEME_DARK else THEME_DARK
        self._theme_btn = self._button(
            controls,
            f"{target_theme.title()} mode",
            self._toggle_theme,
            width=96,
            height=32,
            border=True,
            text_color=self.ui.text_muted,
        )
        self._theme_btn.grid(row=0, column=2, padx=(0, 8))

        self._button(
            controls,
            "Prompts",
            self.show_prompts,
            width=78,
            height=32,
            border=True,
            text_color=self.ui.text_muted,
        ).grid(row=0, column=3, padx=(0, 8))
        self._button(
            controls,
            "Settings",
            self.show_settings,
            width=84,
            height=32,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            text_color=self.ui.accent_text,
        ).grid(row=0, column=4)

        tk.Frame(header, height=1, bg=self.ui.border).place(relx=0, rely=1, relwidth=1, y=-1)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=self.SIDEBAR_W, fg_color=self.ui.sidebar)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(4, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=18, pady=(22, 16), sticky="ew")
        brand.grid_columnconfigure(1, weight=1)

        mark = ctk.CTkFrame(
            brand,
            width=42,
            height=42,
            fg_color=self.ui.accent_soft,
            corner_radius=12,
            border_width=1,
            border_color=self.ui.border,
        )
        mark.grid(row=0, column=0, padx=(0, 12), sticky="w")
        mark.grid_propagate(False)
        self._label(mark, "D", 24, "bold", color=self.ui.accent).place(
            relx=0.5, rely=0.5, anchor="center"
        )

        self._label(brand, APP_NAME, 25, "bold").grid(row=0, column=1, sticky="sw")
        self._label(brand, "Local-first development", 11, color=self.ui.text_subtle).grid(
            row=1, column=1, sticky="nw"
        )

        self._button(
            self.sidebar,
            "+  New chat",
            self.new_chat,
            height=42,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            text_color=self.ui.accent_text,
            radius=10,
            font=self._font(14, "bold"),
        ).grid(row=1, column=0, padx=18, pady=(0, 16), sticky="ew")

        if not hasattr(self, "_search_trace_registered"):
            self._search_var.trace_add("write", lambda *_: self.refresh_sidebar())
            self._search_trace_registered = True
        search = ctk.CTkEntry(
            self.sidebar,
            textvariable=self._search_var,
            placeholder_text="Search chats",
            fg_color=self.ui.sidebar_alt,
            border_color=self.ui.border,
            border_width=1,
            text_color=self.ui.text,
            placeholder_text_color=self.ui.text_subtle,
            corner_radius=10,
            height=36,
            font=self._font(12),
        )
        search.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="ew")

        self._label(self.sidebar, "Recent", 12, "bold", color=self.ui.text_muted, anchor="w").grid(
            row=3, column=0, padx=20, pady=(0, 4), sticky="ew"
        )

        self.session_list = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=self.ui.border_strong,
            scrollbar_button_hover_color=self.ui.accent_soft,
        )
        self.session_list.grid(row=4, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.session_list.grid_columnconfigure(0, weight=1)

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.grid(row=5, column=0, padx=18, pady=(0, 14), sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        self._sidebar_nav(nav, "Projects", "Project grouping is not configured yet.", 0)
        self._sidebar_nav(nav, "Artifacts", "Generated outputs will appear in the workspace rail.", 1)
        self._sidebar_nav(nav, "Settings", "Provider, model, and appearance controls.", 2)

        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.grid(row=6, column=0, padx=18, pady=(0, 16), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self._label(
            footer,
            "Local",
            12,
            "bold",
            color=self.ui.success,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._label(
            footer,
            f"{self.provider_name} - {self.model_name}",
            10,
            color=self.ui.text_subtle,
            anchor="w",
            wraplength=240,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        tk.Frame(self.sidebar, width=1, bg=self.ui.border).place(
            relx=1.0, rely=0, relheight=1, x=-1
        )
        self.refresh_sidebar()

    def _sidebar_nav(self, parent, title: str, description: str, row: int):
        command = self.show_settings if title == "Settings" else None
        frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            corner_radius=10,
            border_width=1,
            border_color=self.ui.border,
        )
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        self._label(frame, title, 13, "bold", anchor="w").grid(
            row=0, column=0, padx=12, pady=(9, 0), sticky="ew"
        )
        self._label(
            frame,
            description,
            10,
            color=self.ui.text_subtle,
            anchor="w",
            wraplength=230,
            justify="left",
        ).grid(row=1, column=0, padx=12, pady=(1, 9), sticky="ew")
        if command:
            for widget in [frame] + list(frame.winfo_children()):
                widget.bind("<Button-1>", lambda _event: command())
                widget.configure(cursor="hand2")

    def refresh_sidebar(self):
        for widget in self.session_list.winfo_children():
            widget.destroy()
        query = self._search_var.get().lower().strip()
        sessions = session_mgr.list_sessions(include_auto=True)
        if query:
            sessions = [session for session in sessions if query in self._session_title(session).lower()]
        if not sessions:
            message = "No matches." if query else "No history yet."
            self._label(self.session_list, message, 12, color=self.ui.text_subtle).grid(
                padx=14, pady=12, sticky="w"
            )
            return
        for session in sessions[:60]:
            self._make_session_item(session)

    def _make_session_item(self, session: dict):
        active = session.get("session_id", session["name"]) == self._session_id
        frame = ctk.CTkFrame(
            self.session_list,
            fg_color=self.ui.selected if active else "transparent",
            corner_radius=10,
            border_width=1 if active else 0,
            border_color=self.ui.border,
        )
        frame.grid(sticky="ew", pady=2, padx=4)
        frame.grid_columnconfigure(0, weight=1)

        self._label(
            frame,
            self._session_title(session),
            12,
            "bold" if active else "normal",
            color=self.ui.text if active else self.ui.text_muted,
            anchor="w",
            justify="left",
            wraplength=220,
        ).grid(row=0, column=0, padx=12, pady=(9, 1), sticky="ew")
        self._label(
            frame,
            self._format_date(session["updated"]),
            10,
            color=self.ui.accent if active else self.ui.text_subtle,
            anchor="w",
        ).grid(row=1, column=0, padx=12, pady=(0, 9), sticky="w")

        filename = session["filename"]

        def click(_event=None, selected_file=filename):
            self.load_session(selected_file)

        def enter(_event=None, item=frame):
            if not active:
                item.configure(fg_color=self.ui.surface_hover)

        def leave(_event=None, item=frame):
            item.configure(fg_color=self.ui.selected if active else "transparent")

        for widget in [frame] + list(frame.winfo_children()):
            widget.bind("<Button-1>", click)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.configure(cursor="hand2")

    def _build_chat_area(self):
        self._chat = ctk.CTkFrame(self, fg_color=self.ui.main, corner_radius=0)
        self._chat.grid(row=1, column=1, sticky="nsew")
        self._chat.grid_columnconfigure(0, weight=1)
        self._chat.grid_rowconfigure(1, weight=1)

        welcome = ctk.CTkFrame(self._chat, fg_color="transparent")
        welcome.grid(row=0, column=0, sticky="ew", padx=42, pady=(26, 14))
        welcome.grid_columnconfigure(0, weight=1)

        self._label(welcome, "What do you want to build?", 30, "bold", anchor="center").grid(
            row=0, column=0, sticky="ew"
        )
        self._label(
            welcome,
            "Dan works locally with your projects, tools, and saved context.",
            14,
            color=self.ui.text_muted,
            anchor="center",
        ).grid(row=1, column=0, pady=(6, 14), sticky="ew")

        starters = ctk.CTkFrame(welcome, fg_color="transparent")
        starters.grid(row=2, column=0)
        prompts = [
            ("Review repo", "Review this repository and identify the highest-risk issues."),
            ("Plan feature", "Help me plan a production-grade feature in this codebase."),
            ("Debug issue", "Help me debug a failing workflow with evidence before fixes."),
        ]
        for index, (label, prompt) in enumerate(prompts):
            self._button(
                starters,
                label,
                lambda value=prompt: self._inject_prompt(value),
                height=30,
                radius=15,
                border=True,
                text_color=self.ui.text_muted,
            ).grid(row=0, column=index, padx=(0, 8))

        board = ctk.CTkFrame(
            self._chat,
            fg_color=self.ui.background,
            corner_radius=18,
            border_width=1,
            border_color=self.ui.border,
        )
        board.grid(row=1, column=0, sticky="nsew", padx=34, pady=(0, 12))
        board.grid_columnconfigure(0, weight=1)
        board.grid_rowconfigure(0, weight=1)

        self.messages_container = ctk.CTkScrollableFrame(
            board,
            fg_color="transparent",
            corner_radius=14,
            scrollbar_button_color=self.ui.border_strong,
            scrollbar_button_hover_color=self.ui.accent_soft,
        )
        self.messages_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.messages_container.grid_columnconfigure(0, weight=1)

        self._build_input_area()

    def _build_input_area(self):
        outer = ctk.CTkFrame(self._chat, fg_color="transparent")
        outer.grid(row=2, column=0, sticky="ew", padx=34, pady=(0, 22))
        outer.grid_columnconfigure(0, weight=1)

        composer = ctk.CTkFrame(
            outer,
            fg_color=self.ui.surface,
            corner_radius=18,
            border_width=1,
            border_color=self.ui.border_strong,
        )
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkTextbox(
            composer,
            height=86,
            fg_color=self.ui.input_bg,
            border_width=0,
            corner_radius=14,
            font=self._font(14),
            text_color=self.ui.text,
            wrap="word",
        )
        self.input_box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.input_box.bind("<Return>", self._handle_enter)
        self.input_box.bind("<Shift-Return>", lambda _event: None)

        bottom = ctk.CTkFrame(composer, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(2, weight=1)

        self._button(
            bottom,
            "Attach",
            self.attach_file,
            width=72,
            height=32,
            border=True,
            text_color=self.ui.text_muted,
        ).grid(row=0, column=0, padx=(0, 8))
        self._button(
            bottom,
            "Actions",
            self.show_actions,
            width=78,
            height=32,
            border=True,
            text_color=self.ui.text_muted,
        ).grid(row=0, column=1, padx=(0, 8))

        self.model_var = tk.StringVar(value=self.model_name)
        ctk.CTkOptionMenu(
            bottom,
            variable=self.model_var,
            values=MODEL_CHOICES,
            width=210,
            height=32,
            corner_radius=10,
            fg_color=self.ui.surface_alt,
            button_color=self.ui.border_strong,
            button_hover_color=self.ui.accent_soft,
            text_color=self.ui.text_muted,
            font=self._font(12),
            command=self.change_model,
        ).grid(row=0, column=3, padx=(8, 8))

        self.send_btn = ctk.CTkButton(
            bottom,
            text="Send",
            width=78,
            height=34,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            text_color=self.ui.accent_text,
            corner_radius=10,
            font=self._font(13, "bold"),
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=4)

    def _build_right_rail(self):
        rail = ctk.CTkFrame(self, width=self.RIGHT_RAIL_W, fg_color=self.ui.main, corner_radius=0)
        rail.grid(row=1, column=2, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(5, weight=1)

        tk.Frame(rail, width=1, bg=self.ui.border).place(x=0, y=0, relheight=1)

        self._label(rail, "Workspace", 13, "bold", color=self.ui.text_muted, anchor="w").grid(
            row=0, column=0, padx=18, pady=(14, 6), sticky="ew"
        )

        panes = [
            ("Files", "Attach or inspect project files through chat.", "Available"),
            ("Tools", "View registered local tools and actions.", "Available"),
            ("Preview", "No rendered preview is open.", "Empty"),
            ("Terminal", "Commands run through secured chat tools.", "Guarded"),
        ]
        for index, pane in enumerate(panes, start=1):
            self._workspace_button(rail, *pane, row=index)

        footer = ctk.CTkFrame(rail, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="sew", padx=18, pady=(6, 12))
        self._label(
            footer,
            "Pane content opens only when backed by a real workflow.",
            9,
            color=self.ui.text_subtle,
            anchor="w",
            wraplength=218,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        self._select_workspace_pane(self._workspace_pane)

    def _workspace_button(self, parent, title: str, description: str, status: str, row: int):
        frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=12)
        frame.grid(row=row, column=0, padx=16, pady=(0, 4), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        self._label(frame, title, 13, "bold", anchor="w").grid(
            row=0, column=0, padx=12, pady=(7, 0), sticky="ew"
        )
        self._label(
            frame,
            description,
            9,
            color=self.ui.text_subtle,
            anchor="w",
            wraplength=210,
        ).grid(row=1, column=0, padx=12, pady=(1, 0), sticky="ew")
        self._label(frame, status, 9, "bold", color=self.ui.accent, anchor="w").grid(
            row=2, column=0, padx=12, pady=(0, 7), sticky="ew"
        )

        def click(_event=None, pane=title):
            self._select_workspace_pane(pane)

        for widget in [frame] + list(frame.winfo_children()):
            widget.bind("<Button-1>", click)
            widget.configure(cursor="hand2")
        self._workspace_buttons[title] = frame

    def _select_workspace_pane(self, pane: str):
        self._workspace_pane = pane
        for title, button in self._workspace_buttons.items():
            button.configure(fg_color=self.ui.selected if title == pane else "transparent")

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, height=34, fg_color=self.ui.main, corner_radius=0)
        bar.grid(row=2, column=1, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)
        bar.grid_propagate(False)
        tk.Frame(bar, height=1, bg=self.ui.border).place(relx=0, rely=0, relwidth=1)

        self._status_dot = self._label(bar, "●", 11, color=self.ui.success)
        self._status_dot.grid(row=0, column=0, padx=(16, 6), sticky="w")
        self._status_txt = self._label(bar, "Ready", 10, color=self.ui.text_muted)
        self._status_txt.grid(row=0, column=1, sticky="w")

        shortcuts = self._label(
            bar,
            "Ctrl+N New - Ctrl+P Prompts - Ctrl+, Settings - Esc Interrupt",
            9,
            color=self.ui.text_subtle,
            anchor="center",
        )
        shortcuts.grid(row=0, column=2, sticky="ew")

        self._status_lbl = self._label(
            bar,
            f"{self.provider_name} - {self.model_name}",
            10,
            color=self.ui.text_subtle,
            anchor="e",
        )
        self._status_lbl.grid(row=0, column=3, sticky="e", padx=(8, 12))

        self._token_lbl = self._label(bar, "", 10, color=self.ui.text_subtle, anchor="e")
        self._token_lbl.grid(row=0, column=4, sticky="e", padx=(0, 14))

    def _inject_prompt(self, text: str):
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self.input_box.focus()

    def add_message(self, role: str, content: str):
        if role == "user":
            self._add_user_message(content)
        elif role == "error":
            self._add_error_message(content)
        else:
            self._add_assistant_message(content)
        self._scroll_to_bottom()

    def _add_user_message(self, content: str):
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 10))
        outer.grid_columnconfigure(0, weight=1)

        bubble = ctk.CTkFrame(
            outer,
            fg_color=self.ui.user_bubble,
            corner_radius=16,
            border_width=1,
            border_color=self.ui.border,
        )
        bubble.grid(row=0, column=1, sticky="e")
        bubble.grid_columnconfigure(0, weight=1)

        textbox = self._message_textbox(bubble, content, self.ui.user_text, max_height=420)
        textbox.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="ew")
        self._label(
            bubble,
            timestamp_label(),
            10,
            color=self.ui.text_subtle,
            anchor="e",
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="e")
        self._attach_copy_hover(bubble, textbox)

    def _add_assistant_message(self, content: str):
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 10))
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_columnconfigure(2, minsize=84, weight=0)

        avatar = ctk.CTkFrame(
            outer,
            width=32,
            height=32,
            fg_color=self.ui.accent_soft,
            corner_radius=16,
            border_width=1,
            border_color=self.ui.border,
        )
        avatar.grid(row=0, column=0, padx=(0, 10), sticky="n", pady=(4, 0))
        avatar.grid_propagate(False)
        self._label(avatar, "D", 14, "bold", color=self.ui.accent).place(
            relx=0.5, rely=0.5, anchor="center"
        )

        bubble = ctk.CTkFrame(
            outer,
            fg_color=self.ui.assistant_bubble,
            corner_radius=16,
            border_width=1,
            border_color=self.ui.border,
        )
        bubble.grid(row=0, column=1, sticky="ew")
        bubble.grid_columnconfigure(0, weight=1)

        textbox = self._message_textbox(bubble, content, self.ui.text, max_height=520)
        textbox.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="ew")
        self._label(
            bubble,
            timestamp_label(),
            10,
            color=self.ui.text_subtle,
            anchor="w",
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="w")
        self._attach_copy_hover(bubble, textbox)

    def _message_textbox(self, parent, content: str, text_color: str, max_height: int):
        textbox = ctk.CTkTextbox(
            parent,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            wrap="word",
            font=self._font(14),
            text_color=text_color,
            activate_scrollbars=False,
        )
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")
        lines = int(textbox.index("end-1c").split(".")[0])
        textbox.configure(height=min(max(lines * 22 + 16, 46), max_height))
        return textbox

    def _add_error_message(self, content: str):
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 10))
        outer.grid_columnconfigure(0, weight=1)
        bubble = ctk.CTkFrame(
            outer,
            fg_color=self.ui.surface,
            corner_radius=14,
            border_width=1,
            border_color=self.ui.error,
        )
        bubble.grid(row=0, column=0, sticky="ew")
        self._label(
            bubble,
            f"Warning: {content}",
            13,
            color=self.ui.error,
            anchor="w",
            wraplength=760,
        ).grid(padx=14, pady=10, sticky="ew")

    def _attach_copy_hover(self, bubble, textbox):
        def copy_text():
            text = textbox.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(text)

        copy_button = ctk.CTkButton(
            bubble,
            text="Copy",
            width=48,
            height=24,
            fg_color="transparent",
            hover_color=self.ui.surface_hover,
            text_color=self.ui.text_subtle,
            corner_radius=8,
            font=self._font(11),
            command=copy_text,
        )
        copy_button.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=6)
        copy_button.place_forget()

        def show(_event=None):
            copy_button.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=6)

        def hide(_event=None):
            copy_button.place_forget()

        for widget in [bubble, textbox]:
            widget.bind("<Enter>", show)
            widget.bind("<Leave>", hide)

    def send_message(self):
        text = self.input_box.get("1.0", "end-1c").strip()
        if not text or self.is_processing:
            return

        self.input_box.delete("1.0", "end")
        self.add_message("user", text)
        self.is_processing = True
        self.send_btn.configure(state="disabled", fg_color=self.ui.accent_soft)
        self._status_dot.configure(text_color=self.ui.warning)
        self._status_txt.configure(text="Generating...")

        bubble = ModernLiveBubble(self.messages_container, self.ui, self._font)
        self._scroll_to_bottom()

        def stream_cb(chunk):
            self.after(0, lambda value=chunk: bubble.append_text(value))
            self.after(10, self._scroll_to_bottom)

        def progress_cb(event, message, data):
            if event == "tool_start":
                self.after(0, lambda value=message: bubble.add_tool_line(f"Tool: {value}"))
                self.after(10, self._scroll_to_bottom)
            elif event == "tool_done" and message:
                self.after(0, lambda value=message: bubble.add_tool_line(f"Done: {value}"))
                self.after(10, self._scroll_to_bottom)

        def process():
            try:
                response, self.messages = run_agent_loop(
                    text,
                    self.messages,
                    self.provider,
                    stream_callback=stream_cb,
                    on_progress=progress_cb,
                )
                self.after(0, lambda: bubble.finish(response))
            except AgentInterrupted:
                self.after(0, lambda: bubble.finish("Paused - type /resume to continue."))
            except Exception as exc:
                self.after(0, lambda error=str(exc): bubble.finish(f"Error: {error}"))
            finally:
                self.after(0, self._finish_processing)

        threading.Thread(target=process, daemon=True).start()

    def _finish_processing(self):
        self.is_processing = False
        self.send_btn.configure(state="normal", fg_color=self.ui.accent)
        self._status_dot.configure(text_color=self.ui.success)
        self._status_txt.configure(text="Ready")
        self._update_tokens()
        self.input_box.focus()
        self._scroll_to_bottom()

        def save_session():
            session_mgr.auto_save(
                self.messages[:], self.provider_name, self.model_name, self._session_id
            )
            self.after(0, self.refresh_sidebar)

        threading.Thread(target=save_session, daemon=True).start()

    def _update_tokens(self):
        count = estimate_tokens(self.messages)
        self._token_lbl.configure(text=f"~{count:,} tokens" if count else "")

    def new_chat(self):
        if self.is_processing:
            return
        self.messages = []
        self._session_id = str(uuid.uuid4())[:8]
        self._clear_chat()
        self._update_tokens()
        self.add_message(
            "assistant",
            f"Hey. I'm {APP_NAME}, your local-first development assistant.\n"
            "Ask me to inspect code, plan a change, debug a workflow, or build something.",
        )
        self.refresh_sidebar()

    def load_session(self, filename: str):
        super().load_session(filename)
        self._status_lbl.configure(text=f"{self.provider_name} - {self.model_name}")

    def _load_history(self) -> bool:
        try:
            saves = sorted(
                (USER_DATA_DIR / "sessions").glob("_auto_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not saves:
                return False
            data = json.loads(saves[0].read_text(encoding="utf-8"))
            messages = data.get("messages", [])
            if not messages:
                return False
            self.messages = messages
            self._session_id = data.get("session_id", self._session_id)
            self._render_messages(messages)
            self._update_tokens()
            return True
        except Exception:
            return False

    def _render_messages(self, messages: list):
        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            if role == "user" and isinstance(content, str) and content.strip():
                self.add_message("user", content)
            elif role == "assistant":
                text = extract_assistant_text(content)
                if text:
                    self.add_message("assistant", text)

    def attach_file(self):
        from tkinter import filedialog

        filename = filedialog.askopenfilename()
        if filename:
            self.input_box.insert("end", f"\n[Attached: {Path(filename).name}]")

    def change_model(self, model: str):
        self.model_name = model
        self.provider_name = infer_provider_from_model(model)
        try:
            self.provider = get_provider(self.provider_name, self.model_name)
            from api_config import load_config, save_config

            config = load_config()
            config["provider"] = self.provider_name
            config.setdefault(self.provider_name, {})["model"] = self.model_name
            save_config(config)
            self._model_lbl.configure(text=f"  {model}  ")
            self._provider_lbl.configure(text=f"  {self.provider_name}  ")
            self._status_lbl.configure(text=f"{self.provider_name} - {model}")
        except Exception as exc:
            self._inline_error(f"Failed to switch model: {exc}")

    def show_settings(self):
        from api_config import get_secret, load_config, save_config, set_secret

        config = load_config()
        window = self._popup("Settings", 540, 650)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            window,
            fg_color="transparent",
            scrollbar_button_color=self.ui.border_strong,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        section_grid = {"padx": 24, "sticky": "ew"}

        self._label(scroll, "Settings", 22, "bold").grid(
            row=0, column=0, pady=(24, 5), **section_grid
        )

        def section(row: int, title: str):
            self._label(scroll, title, 10, "bold", color=self.ui.text_subtle, anchor="w").grid(
                row=row, column=0, pady=(16, 4), **section_grid
            )

        def entry(row: int, var, **kwargs):
            ctk.CTkEntry(
                scroll,
                textvariable=var,
                fg_color=self.ui.input_bg,
                border_color=self.ui.border,
                text_color=self.ui.text,
                border_width=1,
                font=self._font(13),
                **kwargs,
            ).grid(row=row, column=0, pady=(0, 4), **section_grid)

        section(1, "APPEARANCE")
        theme_var = tk.StringVar(value=self._theme_name)
        ctk.CTkOptionMenu(
            scroll,
            variable=theme_var,
            values=[THEME_DARK, THEME_LIGHT],
            fg_color=self.ui.surface,
            button_color=self.ui.border_strong,
            button_hover_color=self.ui.accent_soft,
            text_color=self.ui.text,
            font=self._font(13),
            corner_radius=8,
        ).grid(row=2, column=0, pady=(0, 4), **section_grid)

        section(3, "PROVIDER")
        provider_var = tk.StringVar(value=config.get("provider", "ollama"))
        ctk.CTkOptionMenu(
            scroll,
            variable=provider_var,
            values=["ollama", "anthropic", "openai", "venice"],
            fg_color=self.ui.surface,
            button_color=self.ui.border_strong,
            button_hover_color=self.ui.accent_soft,
            text_color=self.ui.text,
            font=self._font(13),
            corner_radius=8,
        ).grid(row=4, column=0, pady=(0, 4), **section_grid)

        section(5, "OLLAMA MODEL")
        ollama_model = tk.StringVar(value=config.get("ollama", {}).get("model", ""))
        entry(6, ollama_model, placeholder_text="e.g. qwen2.5-coder:14b")

        section(7, "OLLAMA URL")
        ollama_url = tk.StringVar(
            value=config.get("ollama", {}).get("base_url", "http://localhost:11434")
        )
        entry(8, ollama_url)

        section(9, "ANTHROPIC API KEY")
        anthropic_key = tk.StringVar(
            value=get_secret("anthropic.api_key") or os.environ.get("ANTHROPIC_API_KEY_1", "")
        )
        entry(10, anthropic_key, show="*", placeholder_text="sk-ant-...")

        section(11, "OPENAI API KEY")
        openai_key = tk.StringVar(value=get_secret("openai.api_key"))
        entry(12, openai_key, show="*", placeholder_text="sk-...")

        section(13, "VENICE API KEY")
        venice_key = tk.StringVar(value=get_secret("venice.api_key"))
        entry(14, venice_key, show="*", placeholder_text="venice-...")

        footer = ctk.CTkFrame(
            window,
            fg_color=self.ui.surface,
            corner_radius=0,
            border_width=1,
            border_color=self.ui.border,
        )
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        saved_var = tk.StringVar()
        self._label(footer, "", 11, color=self.ui.success, anchor="w", textvariable=saved_var).grid(
            row=0, column=0, padx=24, pady=(10, 0), sticky="ew"
        )

        def save_settings():
            selected_theme = normalize_theme(theme_var.get())
            config["provider"] = provider_var.get()
            config.setdefault("ui", {})["theme"] = selected_theme
            config.setdefault("ollama", {})["model"] = ollama_model.get().strip()
            config.setdefault("ollama", {})["base_url"] = ollama_url.get().strip()
            save_config(config)
            set_secret("anthropic.api_key", anthropic_key.get())
            set_secret("openai.api_key", openai_key.get())
            set_secret("venice.api_key", venice_key.get())

            provider_name = provider_var.get()
            model_name = ollama_model.get().strip()
            try:
                self.provider = get_provider(
                    provider_name,
                    model_name if provider_name == "ollama" else self.model_name,
                )
                self.provider_name = provider_name
                if provider_name == "ollama":
                    self.model_name = model_name
                    self.model_var.set(model_name)
                    self._model_lbl.configure(text=f"  {model_name}  ")
            except Exception:
                pass

            saved_var.set("Saved")
            if selected_theme != self._theme_name:
                window.after(150, window.destroy)
                self.after(180, lambda: self._set_theme(selected_theme, persist=False))
            else:
                self._status_lbl.configure(text=f"{self.provider_name} - {self.model_name}")
                window.after(900, window.destroy)

        ctk.CTkButton(
            footer,
            text="Save settings",
            height=40,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            corner_radius=10,
            text_color=self.ui.accent_text,
            font=self._font(14, "bold"),
            command=save_settings,
        ).grid(row=1, column=0, padx=24, pady=(8, 16), sticky="ew")

    def show_actions(self):
        actions = get_all_actions()
        lines = "\n".join(f"/{action.name} - {action.description}" for action in actions.values())
        window = self._popup("Actions", 540, 500)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        self._label(window, "Available Actions", 18, "bold").grid(
            row=0, column=0, padx=24, pady=(22, 12), sticky="w"
        )
        textbox = ctk.CTkTextbox(
            window,
            fg_color=self.ui.input_bg,
            border_color=self.ui.border,
            border_width=1,
            corner_radius=12,
            font=self._font(13),
            text_color=self.ui.text,
            wrap="word",
        )
        textbox.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        textbox.insert("1.0", lines or "No actions registered.")
        textbox.configure(state="disabled")

    def _toggle_theme(self):
        target = THEME_LIGHT if self._theme_name == THEME_DARK else THEME_DARK
        self._set_theme(target)

    def _set_theme(self, theme_name: str, *, persist: bool = True):
        if self.is_processing:
            self._inline_error("Finish the current response before switching theme.")
            return
        selected_theme = normalize_theme(theme_name)
        if persist:
            from api_config import load_config, save_config

            config = load_config()
            config.setdefault("ui", {})["theme"] = selected_theme
            save_config(config)
        self._theme_name = selected_theme
        self.ui = get_theme_tokens(selected_theme)
        self._rebuild_ui_preserving_messages()

    def _rebuild_ui_preserving_messages(self):
        messages = list(self.messages)
        for widget in self.winfo_children():
            widget.destroy()
        self._workspace_buttons = {}
        self._build_ui()
        self._render_messages(messages)
        self._update_tokens()
        self.input_box.focus()

    # ------------------------------------------------------------------
    # Dialog windows (previously inherited from DanGUI)
    # ------------------------------------------------------------------

    def show_prompts(self) -> None:
        """Open the prompt library dialog using the current theme."""
        pdir = USER_DATA_DIR / "prompts"
        pdir.mkdir(parents=True, exist_ok=True)

        window = self._popup("Prompts", 840, 600)
        window.grid_columnconfigure(1, weight=1)
        window.grid_rowconfigure(0, weight=1)

        # ── Left pane: prompt list ────────────────────────────────────────
        left = ctk.CTkFrame(window, fg_color=self.ui.sidebar, corner_radius=0, width=230)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self._button(
            left,
            "+  New prompt",
            lambda: _load(None),
            height=38,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            text_color=self.ui.accent_text,
            radius=10,
        ).grid(row=0, column=0, padx=12, pady=(14, 8), sticky="ew")

        prompt_list = ctk.CTkScrollableFrame(
            left,
            fg_color="transparent",
            scrollbar_button_color=self.ui.border_strong,
        )
        prompt_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        prompt_list.grid_columnconfigure(0, weight=1)

        # ── Right pane: editor ────────────────────────────────────────────
        right = ctk.CTkFrame(window, fg_color=self.ui.background, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        name_row = ctk.CTkFrame(right, fg_color="transparent")
        name_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        name_row.grid_columnconfigure(1, weight=1)
        self._label(name_row, "Name", 10, "bold", color=self.ui.text_subtle, anchor="w").grid(
            row=0, column=0, padx=(0, 10)
        )
        name_var = tk.StringVar()
        ctk.CTkEntry(
            name_row,
            textvariable=name_var,
            placeholder_text="Prompt name...",
            fg_color=self.ui.input_bg,
            border_color=self.ui.border,
            border_width=1,
            text_color=self.ui.text,
            font=self._font(13),
        ).grid(row=0, column=1, sticky="ew")

        editor = ctk.CTkTextbox(
            right,
            fg_color=self.ui.input_bg,
            border_width=1,
            border_color=self.ui.border,
            corner_radius=12,
            text_color=self.ui.text,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
        )
        editor.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))

        _cur: list = [None]

        def _refresh() -> None:
            for w in prompt_list.winfo_children():
                w.destroy()
            files = sorted(pdir.glob("*.txt"))
            if not files:
                self._label(
                    prompt_list, "No prompts yet.", 12, color=self.ui.text_subtle
                ).grid(padx=10, pady=10, sticky="w")
                return
            for fp in files:
                active = fp == _cur[0]
                self._button(
                    prompt_list,
                    fp.stem,
                    lambda f=fp: _load(f),
                    height=34,
                    fg_color=self.ui.surface if active else "transparent",
                    hover_color=self.ui.surface_hover,
                    text_color=self.ui.text if active else self.ui.text_muted,
                    radius=8,
                ).grid(sticky="ew", pady=2, padx=2)

        def _load(fp) -> None:
            _cur[0] = fp
            editor.delete("1.0", "end")
            if fp is None:
                name_var.set("")
                editor.insert("1.0", DEFAULT_PROMPT_TEMPLATE)
            else:
                name_var.set(fp.stem)
                editor.insert("1.0", fp.read_text(encoding="utf-8"))
            _refresh()

        def _save() -> None:
            safe = sanitize_prompt_name(name_var.get().strip())
            if not safe:
                return
            fp = pdir / f"{safe}.txt"
            fp.write_text(editor.get("1.0", "end-1c"), encoding="utf-8")
            _cur[0] = fp
            _refresh()

        def _delete() -> None:
            if _cur[0] and _cur[0].exists():
                _cur[0].unlink()
            _load(None)

        def _use() -> None:
            text = editor.get("1.0", "end-1c").strip()
            if text:
                self._inject_prompt(text)
            window.destroy()

        self._button(btn_row, "Save", _save, width=80, height=36, border=True).grid(
            row=0, column=0, padx=(0, 8)
        )
        self._button(
            btn_row,
            "Delete",
            _delete,
            width=80,
            height=36,
            fg_color=self.ui.surface,
            hover_color=self.ui.surface_hover,
            text_color=self.ui.text_muted,
        ).grid(row=0, column=1, padx=(0, 8))
        self._button(
            btn_row,
            "Use prompt  ▶",
            _use,
            width=150,
            height=36,
            fg_color=self.ui.accent,
            hover_color=self.ui.accent_hover,
            text_color=self.ui.accent_text,
        ).grid(row=0, column=2)

        _refresh()
        _load(None)

    def show_terminal(self) -> None:
        """Placeholder for the terminal pane."""
        self.add_message(
            "assistant",
            "Terminal view coming soon!\n"
            "For now, ask me to run commands and I'll use the shell tool.",
        )

    def show_error(self, message: str) -> None:
        """Display *message* as an inline error bubble."""
        self._inline_error(message)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _session_title(session: dict) -> str:
        return session_title_from_file(session, USER_DATA_DIR / "sessions")

    @staticmethod
    def _format_date(timestamp: float) -> str:
        return format_relative_date(timestamp)


def _show_fatal_error(title: str, message: str) -> None:
    """Show a native error dialog on Windows; fall back to stderr everywhere else.

    Using tkinter.messagebox keeps this dependency-free (tkinter is always
    available when the GUI path is reachable) and avoids a second ctk import
    during crash handling.
    """
    import sys
    import traceback

    # Always print to stderr so crash details are captured in log files.
    print(f"\n{'='*60}\n{title}\n{message}\n{'='*60}", file=sys.stderr)

    # On Windows, also show a native message box so the error is visible when
    # the user double-clicked the executable and has no console window.
    if sys.platform == "win32":
        try:
            import tkinter as tk  # noqa: PLC0415
            import tkinter.messagebox as mb  # noqa: PLC0415

            root = tk.Tk()
            root.withdraw()
            mb.showerror(title, message)
            root.destroy()
        except Exception:  # noqa: BLE001
            pass  # If tkinter itself fails, we already printed to stderr above.


def _install_exception_hooks() -> None:
    """Install sys.excepthook and threading.excepthook to surface crashes.

    Without these hooks, unhandled exceptions in non-main threads are silently
    swallowed on Windows when there is no console window.  This ensures that
    any crash — whether in the main thread or a background worker — produces a
    visible error dialog.
    """
    import sys
    import threading
    import traceback

    def _handle_main_thread_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            # Let Ctrl+C exit silently — that is intentional.
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _show_fatal_error(
            f"{APP_NAME} — Unexpected Error",
            f"An unexpected error occurred:\n\n{details}",
        )

    def _handle_thread_exception(args):
        if args.exc_type is SystemExit:
            return
        details = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb)
        )
        _show_fatal_error(
            f"{APP_NAME} — Background Thread Error",
            f"A background thread raised an unhandled exception:\n\n{details}",
        )

    sys.excepthook = _handle_main_thread_exception
    threading.excepthook = _handle_thread_exception


def main() -> None:
    _install_exception_hooks()
    ensure_gui_runtime()
    try:
        app = DanModernGUI()
        app.mainloop()
    except Exception as exc:
        _show_fatal_error(f"{APP_NAME} — Fatal Error", str(exc))
        raise
    finally:
        try:
            from workers import get_pool
            get_pool().shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
