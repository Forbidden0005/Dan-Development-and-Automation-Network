#!/usr/bin/env python3
"""Dan GUI — Deep-space dark theme · all features.

.. deprecated::
    This module is the legacy GUI shell and is no longer imported by any
    production path.  ``dan_gui_modern.py`` is the supported desktop entry
    point.  Controller logic previously shared through class inheritance has
    been extracted into ``dan_gui_controller.DanControllerMixin``.

    Caller audit (2026-06-08 steward pass 14): no Python file outside this
    module imports ``dan_gui`` or ``DanGUI``.  The launch scripts
    (``run_gui.bat``, ``run_gui.sh``) invoke ``dan_gui_modern.py`` directly.

    This file is ready for deletion pending explicit user approval (Destructive
    Action Gate).  It is kept in-tree until that approval is given to preserve
    the option of a lightweight fallback shell.
"""

import sys
import threading
import time
import uuid
import json
import os
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent))

import tkinter as tk
from tkinter import filedialog
from gui_compat import ctk, ensure_gui_runtime

from config import APP_NAME, APP_VERSION, USER_DATA_DIR
from dan_gui_components import (
    GradientStrip as ComponentGradientStrip,
    LiveBubble as ComponentLiveBubble,
    button as component_button,
    label as component_label,
    popup_base as component_popup_base,
)
from dan_gui_support import (
    DEFAULT_PROMPT_TEMPLATE,
    build_actions_text,
    estimate_tokens,
    extract_assistant_text,
    format_relative_date,
    infer_provider_from_model,
    register_all_tools,
    sanitize_prompt_name,
    session_title_from_file,
    timestamp_label,
)
from providers import get_provider
from agent import run_agent_loop, AgentInterrupted
from workers import get_pool
from actions import get_all_actions
from tool_registry import get_all_tools
import session_mgr
import cost_tracker

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("dan.gui")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Design tokens ──────────────────────────────────────────────────────────────
BG = "#08080f"
SURFACE = "#0e0e1c"
SURFACE2 = "#13132a"
CARD = "#1a1a32"
CARD_HOV = "#20203c"
BORDER = "#2a2a48"
BORDER2 = "#3a3a60"
PURPLE = "#7c3aed"
PURPLE_HOV = "#9060f5"
PURPLE_DIM = "#4c1d95"
INDIGO = "#4338ca"
TEXT = "#f0f0ff"
TEXT2 = "#9090c0"
TEXT3 = "#50507a"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
ERROR_C = "#ef4444"
ASST_BG = "#12122a"
TOOL_C = "#5a5a90"
MSG_WRAP = 620  # max pixel width before text wraps in bubbles
HEADER_H = 60
SIDEBAR_W = 272


# ── Helpers ────────────────────────────────────────────────────────────────────


def _popup_base(parent, title: str, w: int, h: int) -> ctk.CTkToplevel:
    return component_popup_base(parent, title, w, h, SURFACE)


def _label(parent, text, size=13, weight="normal", color=TEXT, **kw):
    return component_label(parent, text, color, size=size, weight=weight, **kw)


def _btn(parent, text, command, w=None, h=36, fg=CARD, hov=CARD_HOV, radius=10, **kw):
    return component_button(
        parent,
        text,
        command,
        fg,
        hov,
        width=w,
        height=h,
        radius=radius,
        **kw,
    )


def _ts() -> str:
    """Current time as short string for message timestamps."""
    return timestamp_label()


def _est_tokens(messages: list) -> int:
    return estimate_tokens(messages)


# ── Animated thinking dots ─────────────────────────────────────────────────────


class GradientStrip(ComponentGradientStrip):
    def __init__(self, parent, h=2, c1="#7c3aed", c2="#4338ca", **kw):
        super().__init__(parent, color_one=c1, color_two=c2, height=h, **kw)


class LiveBubble(ComponentLiveBubble):
    def __init__(self, parent):
        super().__init__(
            parent,
            assistant_bg=ASST_BG,
            border_color=BORDER,
            purple_dim=PURPLE_DIM,
            card_hover=CARD_HOV,
            text_color=TEXT,
            muted_text_color=TEXT3,
            tool_color=TOOL_C,
        )


# ── Main application ───────────────────────────────────────────────────────────


class DanGUI(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  ·  v{APP_VERSION}")
        self.geometry("1300x860")
        self.configure(fg_color=BG)
        self.minsize(920, 640)

        self.messages = []
        self.provider = None
        self.is_processing = False
        self._session_id = str(uuid.uuid4())[:8]
        self._search_var = tk.StringVar()

        from api_config import load_config
        from config import DEFAULT_PROVIDER, DEFAULT_MODEL

        _cfg = load_config()
        self.provider_name = _cfg.get("provider") or DEFAULT_PROVIDER
        _pc = _cfg.get(self.provider_name, {})
        self.model_name = _pc.get("model") or _cfg.get("model") or DEFAULT_MODEL

        self._init_dan()
        self._build_ui()
        self._bind_shortcuts()

        if not self._load_history():
            self.add_message(
                "assistant",
                f"Hey! I'm {APP_NAME} — your AI development assistant.\n"
                "Ask me anything, paste some code, or tell me what to build.",
            )

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_dan(self):
        # Tool registration is delegated to the canonical entry point so both
        # GUI shells and the CLI share a single implementation.
        register_all_tools()
        try:
            self.provider = get_provider(self.provider_name, self.model_name)
        except Exception as e:
            error_message = str(e)
            self.after(
                500,
                lambda message=error_message: self._inline_error(
                    f"Provider init failed: {message}"
                ),
            )

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        self.bind("<Control-n>", lambda e: self.new_chat())
        self.bind("<Control-l>", lambda e: self.new_chat())
        self.bind("<Control-comma>", lambda e: self.show_settings())
        self.bind("<Control-p>", lambda e: self.show_prompts())
        self.bind("<Escape>", lambda e: self._cancel_if_processing())

    def _cancel_if_processing(self):
        if self.is_processing:
            self._inline_error("Interrupted. Use /resume to continue.")
            self._finish_processing()

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_sidebar()
        self._build_chat_area()
        self._build_status_bar()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        outer = ctk.CTkFrame(self, height=HEADER_H, fg_color=SURFACE, corner_radius=0)
        outer.grid(row=0, column=0, columnspan=2, sticky="ew")
        outer.grid_propagate(False)
        outer.grid_columnconfigure(2, weight=1)

        GradientStrip(outer, h=2, c1=PURPLE, c2=INDIGO, bg=SURFACE).place(x=0, y=0, relwidth=1)

        lf = ctk.CTkFrame(outer, fg_color="transparent")
        lf.grid(row=0, column=0, padx=(18, 8), pady=14, sticky="w")
        ctk.CTkLabel(lf, text="◈", text_color=PURPLE, font=ctk.CTkFont(size=24)).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkLabel(
            lf,
            text=APP_NAME,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=1)

        self._model_badge = ctk.CTkFrame(
            outer, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER2
        )
        self._model_badge.grid(row=0, column=1, padx=14, pady=18, sticky="w")
        self._model_lbl = ctk.CTkLabel(
            self._model_badge,
            text=f"  {self.model_name}  ",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT2,
        )
        self._model_lbl.grid(padx=4, pady=2)

        # Keyboard hint
        ctk.CTkLabel(
            outer,
            text="⌃N  new   ⌃,  settings   ⌃P  prompts",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
        ).grid(row=0, column=3, padx=12, sticky="e")

        self._status_dot = ctk.CTkLabel(
            outer, text="●", text_color=SUCCESS, font=ctk.CTkFont(size=10)
        )
        self._status_dot.grid(row=0, column=4, padx=(0, 4), sticky="e")
        self._status_txt = ctk.CTkLabel(
            outer, text="Ready", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT3
        )
        self._status_txt.grid(row=0, column=5, padx=(0, 12), sticky="e")

        _btn(outer, "⚙", self.show_settings, w=38, h=38, fg=CARD, hov=CARD_HOV, radius=10).grid(
            row=0, column=6, padx=(0, 16), pady=12, sticky="e"
        )

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=SURFACE, corner_radius=0)
        sb.grid(row=1, column=0, sticky="nsew", rowspan=2)
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(3, weight=1)

        tk.Frame(sb, width=1, bg=BORDER).place(relx=1.0, rely=0, relheight=1, x=-1)

        _btn(
            sb,
            "＋  New Chat",
            self.new_chat,
            h=40,
            fg=PURPLE_DIM,
            hov=PURPLE,
            radius=12,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 6), sticky="ew")

        # Search box
        search = ctk.CTkEntry(
            sb,
            textvariable=self._search_var,
            placeholder_text="🔍  Search chats...",
            fg_color=CARD,
            border_color=BORDER,
            border_width=1,
            text_color=TEXT2,
            placeholder_text_color=TEXT3,
            corner_radius=8,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        search.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        self._search_var.trace_add("write", lambda *_: self.refresh_sidebar())

        ctk.CTkLabel(
            sb,
            text="RECENT CHATS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT3,
            anchor="w",
        ).grid(row=2, column=0, padx=18, pady=(4, 4), sticky="w")

        self.session_list = ctk.CTkScrollableFrame(
            sb, fg_color="transparent", corner_radius=0, scrollbar_button_color=BORDER2
        )
        self.session_list.grid(row=3, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.session_list.grid_columnconfigure(0, weight=1)

        self.refresh_sidebar()

    def refresh_sidebar(self):
        for w in self.session_list.winfo_children():
            w.destroy()
        query = self._search_var.get().lower().strip()
        sessions = session_mgr.list_sessions(include_auto=True)
        if query:
            sessions = [s for s in sessions if query in self._session_title(s).lower()]
        if not sessions:
            msg = "No matches." if query else "No history yet."
            _label(self.session_list, msg, 12, color=TEXT3).grid(padx=14, pady=12, sticky="w")
            return
        for s in sessions[:60]:
            self._make_session_item(s)

    def _make_session_item(self, s: dict):
        active = s.get("session_id", s["name"]) == self._session_id
        frame = ctk.CTkFrame(
            self.session_list, fg_color=CARD if active else "transparent", corner_radius=10
        )
        frame.grid(sticky="ew", pady=2, padx=4)
        frame.grid_columnconfigure(1, weight=1)

        if active:
            tk.Frame(frame, width=3, bg=PURPLE).place(x=0, y=6, height=34)

        ctk.CTkLabel(
            frame,
            text="💬",
            width=22,
            font=ctk.CTkFont(size=12),
            text_color=PURPLE if active else TEXT3,
        ).grid(row=0, column=0, padx=(10, 6), pady=8, sticky="w")

        ctk.CTkLabel(
            frame,
            text=self._session_title(s),
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold" if active else "normal"),
            text_color=TEXT if active else TEXT2,
            wraplength=170,
        ).grid(row=0, column=1, padx=(0, 4), pady=(8, 2), sticky="ew")
        ctk.CTkLabel(
            frame,
            text=self._format_date(s["updated"]),
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=PURPLE if active else TEXT3,
        ).grid(row=1, column=1, padx=(0, 4), pady=(0, 8), sticky="w")

        fn = s["filename"]

        def _click(e=None, f=fn):
            self.load_session(f)

        def _enter(e, fr=frame):
            if not active:
                fr.configure(fg_color=CARD_HOV)

        def _leave(e, fr=frame):
            fr.configure(fg_color=CARD if active else "transparent")

        for w in [frame] + list(frame.winfo_children()):
            try:
                w.bind("<Button-1>", _click)
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.configure(cursor="hand2")
            except Exception:
                pass

    def new_chat(self):
        if self.is_processing:
            return
        self.messages = []
        self._session_id = str(uuid.uuid4())[:8]
        self._clear_chat()
        self._update_tokens()
        self.add_message(
            "assistant",
            f"Hey! I'm {APP_NAME} — your AI development assistant.\n"
            "Ask me anything, paste some code, or tell me what to build.",
        )
        self.refresh_sidebar()

    def load_session(self, filename: str):
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
        except Exception as e:
            self._inline_error(f"Could not load session: {e}")

    # ── Chat area ─────────────────────────────────────────────────────────────

    def _build_chat_area(self):
        self._chat = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._chat.grid(row=1, column=1, sticky="nsew")
        self._chat.grid_columnconfigure(0, weight=1)
        self._chat.grid_rowconfigure(0, weight=1)

        self.messages_container = ctk.CTkScrollableFrame(
            self._chat,
            fg_color=BG,
            corner_radius=0,
            scrollbar_button_color=BORDER2,
            scrollbar_button_hover_color=PURPLE_DIM,
        )
        self.messages_container.grid(row=0, column=0, sticky="nsew", padx=32, pady=(20, 0))
        self.messages_container.grid_columnconfigure(0, weight=1)

        self._build_input_area()

    def _build_input_area(self):
        outer = ctk.CTkFrame(self._chat, fg_color=BG, corner_radius=0)
        outer.grid(row=1, column=0, sticky="ew", padx=32, pady=16)
        outer.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            outer, fg_color=SURFACE2, corner_radius=18, border_width=1, border_color=BORDER2
        )
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        _btn(card, "📎", self.attach_file, w=34, h=34, fg=CARD, hov=CARD_HOV, radius=17).grid(
            row=0, column=0, padx=(10, 6), pady=10
        )

        self.input_box = ctk.CTkTextbox(
            card,
            height=44,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT,
            wrap="word",
        )
        self.input_box.grid(row=0, column=1, sticky="ew", pady=10)
        self.input_box.bind("<Return>", self._handle_enter)
        self.input_box.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(
            card,
            text="▶",
            width=42,
            height=42,
            fg_color=PURPLE,
            hover_color=PURPLE_HOV,
            corner_radius=21,
            font=ctk.CTkFont(size=16),
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=2, padx=(6, 10), pady=9)

        # Toolbar
        tb = ctk.CTkFrame(outer, fg_color="transparent")
        tb.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        bs = dict(
            height=30,
            corner_radius=8,
            fg_color=CARD,
            hover_color=CARD_HOV,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT2,
        )
        _btn(tb, "Prompts", self.show_prompts, w=80, **bs).grid(row=0, column=0, padx=(0, 6))
        _btn(tb, "Actions", self.show_actions, w=80, **bs).grid(row=0, column=1, padx=(0, 6))
        _btn(tb, "Terminal", self.show_terminal, w=80, **bs).grid(row=0, column=2, padx=(0, 14))

        self.model_var = tk.StringVar(value=self.model_name)
        ctk.CTkOptionMenu(
            tb,
            variable=self.model_var,
            values=[
                "qwen2.5-coder:14b",
                "qwen2.5-coder:7b",
                "qwen2.5-coder:32b",
                "llama3.1:8b",
                "deepseek-coder-v2:16b",
                "claude-sonnet-4-6",
                "claude-opus-4-20250514",
                "gpt-4o",
                "gpt-4o-mini",
            ],
            width=210,
            height=30,
            corner_radius=8,
            fg_color=CARD,
            button_color=BORDER2,
            button_hover_color=PURPLE_DIM,
            text_color=TEXT2,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.change_model,
        ).grid(row=0, column=3)

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, height=26, fg_color=SURFACE, corner_radius=0)
        bar.grid(row=2, column=1, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        self._status_lbl = ctk.CTkLabel(
            bar,
            text=f"  {self.provider_name}  ·  {self.model_name}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
            anchor="w",
        )
        self._status_lbl.grid(row=0, column=0, sticky="w", padx=8)

        kb = ctk.CTkLabel(
            bar,
            text="Ctrl+N  New    Ctrl+L  Clear    Ctrl+,  Settings    Ctrl+P  Prompts",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=TEXT3,
            anchor="center",
        )
        kb.grid(row=0, column=1, sticky="ew")

        self._token_lbl = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT3, anchor="e"
        )
        self._token_lbl.grid(row=0, column=2, sticky="e", padx=8)

    # ── Messages ──────────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        if role == "user":
            self._add_user_message(content)
        elif role == "error":
            self._add_error_message(content)
        else:
            self._add_assistant_message(content)
        self._scroll_to_bottom()

    def _add_user_message(self, content: str):
        ts = _ts()
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 4))
        outer.grid_columnconfigure(0, weight=1)  # left spacer → pushes bubble right
        outer.grid_columnconfigure(1, weight=0)  # bubble

        wrap = ctk.CTkFrame(outer, fg_color="transparent")
        wrap.grid(row=0, column=1)

        bubble = ctk.CTkFrame(
            wrap, fg_color="#1a2f60", corner_radius=14, border_width=1, border_color="#263d7a"
        )
        bubble.grid(row=0, column=0)
        bubble.grid_columnconfigure(0, weight=1)

        tb = ctk.CTkTextbox(
            bubble,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color="#c8d8ff",
            activate_scrollbars=False,
        )
        tb.grid(row=0, column=0, padx=14, pady=(10, 6), sticky="ew")
        tb.insert("1.0", content)
        tb.configure(state="disabled")
        lines = int(tb.index("end-1c").split(".")[0])
        tb.configure(height=min(max(lines * 22 + 16, 46), 400))

        # Copy on hover
        self._attach_copy_hover(bubble, tb)

        # Timestamp
        ctk.CTkLabel(
            bubble,
            text=ts,
            anchor="e",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="e")

        # Avatar dot
        ctk.CTkLabel(
            wrap, text="◉", width=26, font=ctk.CTkFont(size=10), text_color="#3a5aaa"
        ).grid(row=0, column=1, padx=(8, 0), sticky="n", pady=4)

    def _add_assistant_message(self, content: str):
        ts = _ts()
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 4))
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_columnconfigure(2, minsize=100, weight=0)  # right margin

        av = ctk.CTkFrame(outer, width=36, height=36, fg_color=PURPLE_DIM, corner_radius=18)
        av.grid(row=0, column=0, padx=(0, 10), sticky="n", pady=4)
        av.grid_propagate(False)
        ctk.CTkLabel(
            av,
            text="◈",
            width=36,
            height=36,
            fg_color="transparent",
            font=ctk.CTkFont(size=16),
            text_color="#c4b5fd",
        ).place(relx=0.5, rely=0.5, anchor="center")

        bubble = ctk.CTkFrame(
            outer, fg_color=ASST_BG, corner_radius=14, border_width=1, border_color=BORDER
        )
        bubble.grid(row=0, column=1, sticky="ew")
        bubble.grid_columnconfigure(0, weight=1)

        tb = ctk.CTkTextbox(
            bubble,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT,
            activate_scrollbars=False,
        )
        tb.grid(row=0, column=0, padx=14, pady=(10, 6), sticky="ew")
        tb.insert("1.0", content)
        tb.configure(state="disabled")
        lines = int(tb.index("end-1c").split(".")[0])
        tb.configure(height=min(max(lines * 22 + 16, 46), 500))

        self._attach_copy_hover(bubble, tb)

        ctk.CTkLabel(
            bubble,
            text=ts,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="w")

    def _add_error_message(self, content: str):
        """Inline error bubble — no popup."""
        outer = ctk.CTkFrame(self.messages_container, fg_color="transparent")
        outer.grid(sticky="ew", pady=(0, 8))
        outer.grid_columnconfigure(0, weight=1)

        bubble = ctk.CTkFrame(
            outer, fg_color="#1f0a12", corner_radius=12, border_width=1, border_color="#5a1525"
        )
        bubble.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            bubble,
            text=f"⚠  {content}",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#fb7185",
            wraplength=700,
        ).grid(padx=14, pady=10, sticky="ew")

        self._scroll_to_bottom()

    def _attach_copy_hover(self, bubble, tb):
        """Show a ⎘ copy button when hovering over a message bubble."""

        def _copy():
            text = tb.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(text)

        cb = ctk.CTkButton(
            bubble,
            text="⎘ Copy",
            width=64,
            height=24,
            fg_color=CARD,
            hover_color=CARD_HOV,
            text_color=TEXT3,
            corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            command=_copy,
        )
        cb.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=6)
        cb.place_forget()

        def _show(e):
            cb.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=6)

        def _hide(e):
            cb.place_forget()

        for w in [bubble, tb]:
            try:
                w.bind("<Enter>", _show)
                w.bind("<Leave>", _hide)
            except Exception:
                pass

    # ── Sending ───────────────────────────────────────────────────────────────

    def _handle_enter(self, event):
        if not (event.state & 0x1):
            self.send_message()
            return "break"

    def send_message(self):
        text = self.input_box.get("1.0", "end-1c").strip()
        if not text or self.is_processing:
            return

        self.input_box.delete("1.0", "end")
        self.add_message("user", text)
        self.is_processing = True
        self.send_btn.configure(state="disabled", fg_color=PURPLE_DIM)
        self._status_dot.configure(text_color=WARNING)
        self._status_txt.configure(text="Generating...")

        bubble = LiveBubble(self.messages_container)
        self._scroll_to_bottom()

        def stream_cb(chunk):
            self.after(0, lambda c=chunk: bubble.append_text(c))
            self.after(10, self._scroll_to_bottom)

        def progress_cb(event, message, data):
            if event == "tool_start":
                self.after(0, lambda m=message: bubble.add_tool_line(f"  ⚡  {m}"))
                self.after(10, self._scroll_to_bottom)
            elif event == "tool_done" and message:
                self.after(0, lambda m=message: bubble.add_tool_line(f"     ↳  {m}"))
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
                self.after(0, lambda: bubble.finish("⏸  Paused — type /resume to continue."))
            except Exception as e:
                self.after(0, lambda err=str(e): bubble.finish(f"Error: {err}"))
            finally:
                self.after(0, self._finish_processing)

        threading.Thread(target=process, daemon=True).start()

    def _finish_processing(self):
        self.is_processing = False
        self.send_btn.configure(state="normal", fg_color=PURPLE)
        self._status_dot.configure(text_color=SUCCESS)
        self._status_txt.configure(text="Ready")
        self._update_tokens()
        self.input_box.focus()
        self._scroll_to_bottom()

        def _save():
            session_mgr.auto_save(
                self.messages[:], self.provider_name, self.model_name, self._session_id
            )
            self.after(0, self.refresh_sidebar)

        threading.Thread(target=_save, daemon=True).start()

    def _update_tokens(self):
        n = _est_tokens(self.messages)
        if n:
            self._token_lbl.configure(text=f"~{n:,} tokens  ")
        else:
            self._token_lbl.configure(text="")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _inline_error(self, msg: str):
        self.add_message("error", msg)

    def _clear_chat(self):
        for w in self.messages_container.winfo_children():
            w.destroy()

    def _scroll_to_bottom(self):
        try:
            self.messages_container._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _load_history(self) -> bool:
        try:
            saves = sorted(
                (USER_DATA_DIR / "sessions").glob("_auto_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if not saves:
                return False
            data = json.loads(saves[0].read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            if not msgs:
                return False
            self.messages = msgs
            self._session_id = data.get("session_id", self._session_id)
            self._render_messages(msgs)
            self._update_tokens()
            return True
        except Exception as e:
            logger.warning("Could not load history: %s", e)
            return False

    def _render_messages(self, messages: list):
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                if isinstance(content, str) and content.strip():
                    self.add_message("user", content)
            elif role == "assistant":
                text = extract_assistant_text(content)
                if text:
                    self.add_message("assistant", text)

    def attach_file(self):
        fn = filedialog.askopenfilename()
        if fn:
            self.input_box.insert("end", f"\n[Attached: {Path(fn).name}]")

    def change_model(self, model: str):
        self.model_name = model
        self.provider_name = infer_provider_from_model(model)
        try:
            self.provider = get_provider(self.provider_name, self.model_name)
            from api_config import load_config, save_config

            cfg = load_config()
            cfg["provider"] = self.provider_name
            cfg.setdefault(self.provider_name, {})["model"] = self.model_name
            save_config(cfg)
            self._model_lbl.configure(text=f"  {model}  ")
            self._status_lbl.configure(text=f"  {self.provider_name}  ·  {model}")
        except Exception as e:
            self._inline_error(f"Failed to switch model: {e}")

    @staticmethod
    def _session_title(s: dict) -> str:
        return session_title_from_file(s, USER_DATA_DIR / "sessions")

    @staticmethod
    def _format_date(ts: float) -> str:
        return format_relative_date(ts)

    # ── Windows ───────────────────────────────────────────────────────────────

    def show_settings(self):
        from api_config import get_secret, load_config, save_config, set_secret

        cfg = load_config()
        win = _popup_base(self, "Settings", 520, 580)
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent", scrollbar_button_color=BORDER2)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        S = {"padx": 24, "sticky": "ew"}

        _label(scroll, "Settings", 20, "bold").grid(row=0, column=0, pady=(22, 4), **S)

        def _sec(r, t):
            _label(scroll, t, 10, "bold", color=TEXT3, anchor="w").grid(
                row=r, column=0, pady=(16, 3), **S
            )

        def _ent(r, var, **kw):
            ctk.CTkEntry(
                scroll,
                textvariable=var,
                fg_color=CARD,
                border_color=BORDER2,
                text_color=TEXT,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                **kw,
            ).grid(row=r, column=0, pady=(0, 4), **S)

        _sec(1, "PROVIDER")
        pv = tk.StringVar(value=cfg.get("provider", "ollama"))
        ctk.CTkOptionMenu(
            scroll,
            variable=pv,
            values=["ollama", "anthropic", "openai", "venice"],
            fg_color=CARD,
            button_color=BORDER2,
            button_hover_color=PURPLE_DIM,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=8,
        ).grid(row=2, column=0, pady=(0, 4), **S)

        _sec(3, "OLLAMA MODEL")
        om = tk.StringVar(value=cfg.get("ollama", {}).get("model", ""))
        _ent(4, om, placeholder_text="e.g. qwen2.5-coder:14b")

        _sec(5, "OLLAMA URL")
        ou = tk.StringVar(value=cfg.get("ollama", {}).get("base_url", "http://localhost:11434"))
        _ent(6, ou)

        _sec(7, "ANTHROPIC API KEY")
        ak = tk.StringVar(
            value=get_secret("anthropic.api_key") or os.environ.get("ANTHROPIC_API_KEY_1", "")
        )
        _ent(8, ak, show="•", placeholder_text="sk-ant-...")

        _sec(9, "OPENAI API KEY")
        ok_ = tk.StringVar(value=get_secret("openai.api_key"))
        _ent(10, ok_, show="•", placeholder_text="sk-...")

        _sec(11, "VENICE API KEY")
        vk = tk.StringVar(value=get_secret("venice.api_key"))
        _ent(12, vk, show="•", placeholder_text="venice-...")

        bot = ctk.CTkFrame(
            win, fg_color=SURFACE2, corner_radius=0, border_width=1, border_color=BORDER
        )
        bot.grid(row=1, column=0, sticky="ew")
        bot.grid_columnconfigure(0, weight=1)
        sv = tk.StringVar()
        ctk.CTkLabel(
            bot, textvariable=sv, text_color=SUCCESS, font=ctk.CTkFont(size=11), anchor="w"
        ).grid(row=0, column=0, padx=24, pady=(10, 0), sticky="ew")

        def _save():
            cfg["provider"] = pv.get()
            cfg.setdefault("ollama", {})["model"] = om.get().strip()
            cfg.setdefault("ollama", {})["base_url"] = ou.get().strip()
            save_config(cfg)
            set_secret("anthropic.api_key", ak.get())
            set_secret("openai.api_key", ok_.get())
            set_secret("venice.api_key", vk.get())
            np_, nm_ = pv.get(), om.get().strip()
            try:
                self.provider = get_provider(np_, nm_ if np_ == "ollama" else self.model_name)
                self.provider_name = np_
                if np_ == "ollama":
                    self.model_name = nm_
                    self.model_var.set(nm_)
                    self._model_lbl.configure(text=f"  {nm_}  ")
            except Exception:
                pass
            sv.set("✓ Saved")
            win.after(1400, win.destroy)

        ctk.CTkButton(
            bot,
            text="Save Settings",
            height=40,
            fg_color=PURPLE,
            hover_color=PURPLE_HOV,
            corner_radius=10,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=_save,
        ).grid(row=1, column=0, padx=24, pady=(8, 16), sticky="ew")

    def show_actions(self):
        actions = get_all_actions()
        lines = "\n".join(f"/{a.name}  —  {a.description}" for a in actions.values())
        win = _popup_base(self, "Actions", 520, 480)
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(1, weight=1)
        _label(win, "Available Actions", 17, "bold").grid(
            row=0, column=0, padx=24, pady=(22, 12), sticky="w"
        )
        tb = ctk.CTkTextbox(
            win,
            fg_color=CARD,
            border_color=BORDER2,
            border_width=1,
            corner_radius=12,
            text_color=TEXT2,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        tb.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tb.insert("1.0", lines or "No actions available.")
        tb.configure(state="disabled")

    def show_prompts(self):
        PDIR = USER_DATA_DIR / "prompts"
        PDIR.mkdir(parents=True, exist_ok=True)
        win = _popup_base(self, "Prompts", 820, 580)
        win.grid_columnconfigure(1, weight=1)
        win.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(win, fg_color=SURFACE2, corner_radius=0, width=220)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkButton(
            left,
            text="＋  New Prompt",
            height=36,
            fg_color=PURPLE_DIM,
            hover_color=PURPLE,
            corner_radius=10,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=lambda: _load(None),
        ).grid(row=0, column=0, padx=10, pady=12, sticky="ew")

        pl = ctk.CTkScrollableFrame(left, fg_color="transparent", scrollbar_button_color=BORDER2)
        pl.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 10))
        pl.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(win, fg_color=SURFACE, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        nf = ctk.CTkFrame(right, fg_color="transparent")
        nf.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        nf.grid_columnconfigure(1, weight=1)
        _label(nf, "Name", 10, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, padx=(0, 10))
        nv = tk.StringVar()
        ctk.CTkEntry(
            nf,
            textvariable=nv,
            placeholder_text="Prompt name...",
            fg_color=CARD,
            border_color=BORDER2,
            border_width=1,
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=0, column=1, sticky="ew")

        editor = ctk.CTkTextbox(
            right,
            fg_color=CARD,
            border_width=1,
            border_color=BORDER2,
            corner_radius=12,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
        )
        editor.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))

        br = ctk.CTkFrame(right, fg_color="transparent")
        br.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))

        _cur = [None]

        def _refresh():
            for w in pl.winfo_children():
                w.destroy()
            files = sorted(PDIR.glob("*.txt"))
            if not files:
                _label(pl, "No prompts yet.", 12, color=TEXT3).grid(padx=10, pady=10, sticky="w")
                return
            for fp in files:
                ctk.CTkButton(
                    pl,
                    text=fp.stem,
                    anchor="w",
                    height=34,
                    fg_color=CARD if fp == _cur[0] else "transparent",
                    hover_color=CARD_HOV,
                    corner_radius=8,
                    text_color=TEXT if fp == _cur[0] else TEXT2,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    command=lambda f=fp: _load(f),
                ).grid(sticky="ew", pady=2, padx=2)

        def _load(fp):
            _cur[0] = fp
            editor.delete("1.0", "end")
            if fp is None:
                nv.set("")
                editor.insert("1.0", DEFAULT_PROMPT_TEMPLATE)
            else:
                nv.set(fp.stem)
                editor.insert("1.0", fp.read_text(encoding="utf-8"))
            _refresh()

        def _save():
            name = nv.get().strip()
            safe = sanitize_prompt_name(name)
            if not safe:
                return
            fp = PDIR / f"{safe}.txt"
            fp.write_text(editor.get("1.0", "end-1c"), encoding="utf-8")
            _cur[0] = fp
            _refresh()

        def _del():
            if _cur[0] and _cur[0].exists():
                _cur[0].unlink()
            _load(None)

        def _use():
            txt = editor.get("1.0", "end-1c").strip()
            if txt:
                self.input_box.delete("1.0", "end")
                self.input_box.insert("1.0", txt)
            win.destroy()

        bs2 = dict(height=36, corner_radius=10, font=ctk.CTkFont(family="Segoe UI", size=13))
        ctk.CTkButton(
            br,
            text="Save",
            width=80,
            fg_color=CARD,
            hover_color=CARD_HOV,
            text_color=TEXT,
            **bs2,
            command=_save,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            br,
            text="Delete",
            width=80,
            fg_color="#3f1515",
            hover_color="#5a1f1f",
            text_color="#ffaaaa",
            **bs2,
            command=_del,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            br,
            text="Use Prompt  ▶",
            width=150,
            fg_color=PURPLE_DIM,
            hover_color=PURPLE,
            text_color=TEXT,
            **bs2,
            command=_use,
        ).grid(row=0, column=2)

        _refresh()
        _load(None)

    def show_terminal(self):
        self.add_message(
            "assistant",
            "Terminal view coming soon!\n"
            "For now, ask me to run commands and I'll use the Bash tool.",
        )

    def show_error(self, message: str):
        self._inline_error(message)


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    ensure_gui_runtime()
    app = DanGUI()
    app.mainloop()
    get_pool().shutdown()


if __name__ == "__main__":
    main()
