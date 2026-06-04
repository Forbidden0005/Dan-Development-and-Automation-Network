#!/usr/bin/env python3
"""Modern shell for Dan GUI built on the stable chat controller."""

from __future__ import annotations

import tkinter as tk

from config import APP_NAME, APP_VERSION
from dan_gui import (
    ASST_BG,
    BG,
    BORDER,
    BORDER2,
    CARD,
    CARD_HOV,
    DanGUI,
    ERROR_C,
    HEADER_H,
    INDIGO,
    PURPLE,
    PURPLE_DIM,
    PURPLE_HOV,
    SUCCESS,
    SURFACE,
    SURFACE2,
    TEXT,
    TEXT2,
    TEXT3,
    TOOL_C,
    WARNING,
    _btn,
    _label,
)
from dan_gui_components import GradientStrip
from dan_gui_support import build_actions_text
from actions import get_all_actions
from gui_compat import ctk, ensure_gui_runtime
from tool_registry import get_all_tools
import session_mgr


class ModernLiveBubble(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        from dan_gui import LiveBubble as LegacyLiveBubble

        self._delegate = LegacyLiveBubble(parent)

    def __getattr__(self, item):
        return getattr(self._delegate, item)


class DanModernGUI(DanGUI):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Studio · v{APP_VERSION}")
        self.geometry("1380x900")

    def _shell_counts(self) -> tuple[int, int]:
        return len(session_mgr.list_sessions(include_auto=True)), len(get_all_tools())

    def _apply_shell_metrics(self):
        sessions, tools = self._shell_counts()
        if hasattr(self, "_sessions_stat"):
            self._sessions_stat.configure(text=str(sessions))
        if hasattr(self, "_tools_stat"):
            self._tools_stat.configure(text=str(tools))
        if hasattr(self, "_hero_subtitle"):
            self._hero_subtitle.configure(
                text=f"{sessions} saved chats ready · {tools} tools available · streamlined for focused build sessions"
            )

    def _inject_prompt(self, text: str):
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", text)
        self.input_box.focus()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_sidebar()
        self._build_chat_area()
        self._build_status_bar()

    def _build_header(self):
        outer = ctk.CTkFrame(self, height=HEADER_H + 16, fg_color=SURFACE, corner_radius=0)
        outer.grid(row=0, column=0, columnspan=2, sticky="ew")
        outer.grid_propagate(False)
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_columnconfigure(3, weight=0)

        GradientStrip(outer, color_one=PURPLE, color_two=INDIGO, height=3, bg=SURFACE).place(x=0, y=0, relwidth=1)

        brand = ctk.CTkFrame(outer, fg_color="transparent")
        brand.grid(row=0, column=0, padx=(20, 10), pady=16, sticky="w")
        ctk.CTkLabel(
            brand,
            text="◈",
            text_color=PURPLE,
            font=ctk.CTkFont(size=26),
        ).grid(row=0, column=0, padx=(0, 10))
        title_block = ctk.CTkFrame(brand, fg_color="transparent")
        title_block.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            title_block,
            text=f"{APP_NAME} Studio",
            text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Calm, focused, production-minded development workspace",
            text_color=TEXT3,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        ).grid(row=1, column=0, sticky="w")

        center = ctk.CTkFrame(outer, fg_color="transparent")
        center.grid(row=0, column=1, sticky="ew")
        center.grid_columnconfigure(0, weight=1)
        chips = ctk.CTkFrame(center, fg_color="transparent")
        chips.grid(row=0, column=0)

        self._model_badge = ctk.CTkFrame(chips, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER2)
        self._model_badge.grid(row=0, column=0, padx=(0, 8))
        self._model_lbl = ctk.CTkLabel(
            self._model_badge,
            text=f"  {self.model_name}  ",
            text_color=TEXT2,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        self._model_lbl.grid(padx=4, pady=3)

        self._provider_badge = ctk.CTkFrame(chips, fg_color=SURFACE2, corner_radius=18, border_width=1, border_color=BORDER)
        self._provider_badge.grid(row=0, column=1, padx=(0, 8))
        self._provider_lbl = ctk.CTkLabel(
            self._provider_badge,
            text=f"  {self.provider_name}  ",
            text_color=TEXT3,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        self._provider_lbl.grid(padx=4, pady=3)

        self._status_chip = ctk.CTkFrame(chips, fg_color="#0f1d17", corner_radius=18, border_width=1, border_color="#1f5133")
        self._status_chip.grid(row=0, column=2)
        self._status_dot = ctk.CTkLabel(self._status_chip, text="●", text_color=SUCCESS, font=ctk.CTkFont(size=10))
        self._status_dot.grid(row=0, column=0, padx=(8, 4), pady=3)
        self._status_txt = ctk.CTkLabel(
            self._status_chip,
            text="Ready",
            text_color=TEXT2,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        self._status_txt.grid(row=0, column=1, padx=(0, 10), pady=3)

        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.grid(row=0, column=3, padx=(10, 18), pady=16, sticky="e")
        _btn(actions, "Prompts", self.show_prompts, w=84, h=36, fg=CARD, hov=CARD_HOV).grid(row=0, column=0, padx=(0, 8))
        _btn(actions, "Actions", self.show_actions, w=84, h=36, fg=CARD, hov=CARD_HOV).grid(row=0, column=1, padx=(0, 8))
        _btn(actions, "Settings", self.show_settings, w=88, h=36, fg=PURPLE_DIM, hov=PURPLE).grid(row=0, column=2)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=300, fg_color=SURFACE, corner_radius=0)
        self.sidebar.grid(row=1, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(4, weight=1)

        tk.Frame(self.sidebar, width=1, bg=BORDER).place(relx=1.0, rely=0, relheight=1, x=-1)

        hero = ctk.CTkFrame(self.sidebar, fg_color=SURFACE2, corner_radius=18, border_width=1, border_color=BORDER)
        hero.grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")
        hero.grid_columnconfigure(0, weight=1)
        _label(hero, "Workspace", 11, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, padx=14, pady=(12, 2), sticky="ew")
        _label(hero, "Start a fresh chat, reopen a session, or switch models without losing flow.", 13, color=TEXT2, anchor="w", wraplength=240, justify="left").grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        strip = ctk.CTkFrame(hero, fg_color="transparent")
        strip.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="ew")
        strip.grid_columnconfigure((0, 1), weight=1)
        sessions_card = ctk.CTkFrame(strip, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        sessions_card.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._sessions_stat = ctk.CTkLabel(sessions_card, text="0", text_color=TEXT, font=ctk.CTkFont(size=20, weight="bold"))
        self._sessions_stat.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="w")
        ctk.CTkLabel(sessions_card, text="saved chats", text_color=TEXT3, font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
        tools_card = ctk.CTkFrame(strip, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        tools_card.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        self._tools_stat = ctk.CTkLabel(tools_card, text="0", text_color=TEXT, font=ctk.CTkFont(size=20, weight="bold"))
        self._tools_stat.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="w")
        ctk.CTkLabel(tools_card, text="available tools", text_color=TEXT3, font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
        _btn(hero, "＋  New Chat", self.new_chat, h=40, fg=PURPLE_DIM, hov=PURPLE, radius=12, text_color=TEXT, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        hero.grid_slaves(row=2, column=0)[0].grid_configure(row=3, pady=(0, 12))

        search = ctk.CTkEntry(
            self.sidebar,
            textvariable=self._search_var,
            placeholder_text="Search saved chats...",
            fg_color=CARD,
            border_color=BORDER,
            border_width=1,
            text_color=TEXT2,
            placeholder_text_color=TEXT3,
            corner_radius=12,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        search.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        self._search_var.trace_add("write", lambda *_: self.refresh_sidebar())

        insights = ctk.CTkFrame(self.sidebar, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        insights.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        insights.grid_columnconfigure(0, weight=1)
        _label(insights, "Session flow", 10, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        _label(insights, "Search your recent work, pick up where you left off, and keep the chat loop tidy.", 12, color=TEXT2, anchor="w", wraplength=244, justify="left").grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(
            self.sidebar,
            text="RECENT CHATS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT3,
            anchor="w",
        ).grid(row=3, column=0, padx=18, pady=(0, 4), sticky="w")

        self.session_list = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=BORDER2,
        )
        self.session_list.grid(row=4, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.session_list.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self.sidebar, fg_color=SURFACE2, corner_radius=14, border_width=1, border_color=BORDER)
        footer.grid(row=5, column=0, padx=14, pady=(0, 14), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        _label(footer, "Quick Tips", 10, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, padx=12, pady=(10, 2), sticky="ew")
        _label(footer, "Use Ctrl+N for a new chat, Ctrl+P for prompts, and Esc to interrupt generation.", 12, color=TEXT2, anchor="w", wraplength=240, justify="left").grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")

        self.refresh_sidebar()
        self._apply_shell_metrics()

    def _make_session_item(self, s: dict):
        active = s.get("session_id", s["name"]) == self._session_id
        frame = ctk.CTkFrame(
            self.session_list,
            fg_color=CARD if active else SURFACE2,
            corner_radius=14,
            border_width=1,
            border_color=PURPLE_DIM if active else BORDER,
        )
        frame.grid(sticky="ew", pady=4, padx=4)
        frame.grid_columnconfigure(1, weight=1)

        rail = ctk.CTkFrame(frame, width=6, fg_color=PURPLE if active else SURFACE2, corner_radius=8)
        rail.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(8, 10), pady=8)

        ctk.CTkLabel(
            frame,
            text="💬",
            width=22,
            text_color=PURPLE if active else TEXT3,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, padx=(0, 6), pady=(10, 2), sticky="w")
        ctk.CTkLabel(
            frame,
            text=self._session_title(s),
            anchor="w",
            justify="left",
            wraplength=194,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold" if active else "normal"),
            text_color=TEXT if active else TEXT2,
        ).grid(row=0, column=2, padx=(0, 10), pady=(10, 2), sticky="ew")
        ctk.CTkLabel(
            frame,
            text=self._format_date(s["updated"]),
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=PURPLE if active else TEXT3,
        ).grid(row=1, column=2, padx=(0, 10), pady=(0, 10), sticky="w")

        fn = s["filename"]

        def _click(e=None, f=fn):
            self.load_session(f)

        def _enter(e, fr=frame):
            if not active:
                fr.configure(fg_color=CARD_HOV)

        def _leave(e, fr=frame):
            fr.configure(fg_color=CARD if active else SURFACE2)

        for w in [frame] + list(frame.winfo_children()):
            try:
                w.bind("<Button-1>", _click)
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.configure(cursor="hand2")
            except Exception:
                pass

    def _build_chat_area(self):
        self._chat = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._chat.grid(row=1, column=1, sticky="nsew")
        self._chat.grid_columnconfigure(0, weight=1)
        self._chat.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(self._chat, fg_color=SURFACE, corner_radius=22, border_width=1, border_color=BORDER)
        hero.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 14))
        hero.grid_columnconfigure(0, weight=1)
        _label(hero, "Focused build workspace", 11, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, padx=18, pady=(14, 4), sticky="ew")
        _label(hero, "Ask, inspect, iterate, and keep momentum without fighting the interface.", 18, "bold", color=TEXT, anchor="w").grid(row=1, column=0, padx=18, pady=(0, 4), sticky="ew")
        self._hero_subtitle = _label(hero, "", 12, color=TEXT2, anchor="w")
        self._hero_subtitle.grid(row=2, column=0, padx=18, pady=(0, 10), sticky="ew")
        quick = build_actions_text(get_all_actions())
        _label(hero, quick or "/help  —  No actions registered yet", 12, color=TEXT2, anchor="w", wraplength=820, justify="left").grid(row=3, column=0, padx=18, pady=(0, 10), sticky="ew")

        starters = ctk.CTkFrame(hero, fg_color="transparent")
        starters.grid(row=4, column=0, padx=18, pady=(0, 16), sticky="w")
        prompts = [
            ("Review this repo", "Review this repository and tell me the highest-value next improvements."),
            ("Plan a feature", "Help me plan the next feature with clear implementation steps."),
            ("Fix a bug", "Help me debug a failing workflow and propose the smallest safe fix."),
        ]
        for index, (label_text, prompt_text) in enumerate(prompts):
            _btn(
                starters,
                label_text,
                lambda value=prompt_text: self._inject_prompt(value),
                h=30,
                fg=CARD,
                hov=CARD_HOV,
                radius=15,
                text_color=TEXT2,
                font=ctk.CTkFont(family="Segoe UI", size=11),
            ).grid(row=0, column=index, padx=(0, 8))

        board = ctk.CTkFrame(self._chat, fg_color=SURFACE2, corner_radius=22, border_width=1, border_color=BORDER)
        board.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        board.grid_columnconfigure(0, weight=1)
        board.grid_rowconfigure(0, weight=1)

        self.messages_container = ctk.CTkScrollableFrame(
            board,
            fg_color=BG,
            corner_radius=16,
            scrollbar_button_color=BORDER2,
            scrollbar_button_hover_color=PURPLE_DIM,
        )
        self.messages_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.messages_container.grid_columnconfigure(0, weight=1)

        self._build_input_area()

    def _build_input_area(self):
        outer = ctk.CTkFrame(self._chat, fg_color="transparent", corner_radius=0)
        outer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 18))
        outer.grid_columnconfigure(0, weight=1)

        composer = ctk.CTkFrame(outer, fg_color=SURFACE, corner_radius=20, border_width=1, border_color=BORDER2)
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(1, weight=1)

        rail = ctk.CTkFrame(composer, fg_color="transparent")
        rail.grid(row=0, column=0, padx=(14, 10), pady=12, sticky="ns")
        rail.grid_rowconfigure((0, 1, 2), weight=1)
        _btn(rail, "📎", self.attach_file, w=38, h=38, fg=CARD, hov=CARD_HOV, radius=19).grid(row=0, column=0, pady=(0, 8))
        _btn(rail, "⚙", self.show_settings, w=38, h=38, fg=CARD, hov=CARD_HOV, radius=19).grid(row=1, column=0, pady=(0, 8))
        _btn(rail, "⌘", self.show_actions, w=38, h=38, fg=CARD, hov=CARD_HOV, radius=19).grid(row=2, column=0)

        text_wrap = ctk.CTkFrame(composer, fg_color="transparent")
        text_wrap.grid(row=0, column=1, sticky="ew", pady=12)
        text_wrap.grid_columnconfigure(0, weight=1)
        _label(text_wrap, "Message Dan", 10, "bold", color=TEXT3, anchor="w").grid(row=0, column=0, sticky="ew", padx=(0, 0), pady=(0, 6))
        self.input_box = ctk.CTkTextbox(
            text_wrap,
            height=82,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=16,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT,
            wrap="word",
        )
        self.input_box.grid(row=1, column=0, sticky="ew")
        self.input_box.bind("<Return>", self._handle_enter)
        self.input_box.bind("<Shift-Return>", lambda e: None)
        _label(
            text_wrap,
            "Shift+Enter for a new line · messages stream live with tool progress",
            11,
            color=TEXT3,
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))

        right = ctk.CTkFrame(composer, fg_color="transparent")
        right.grid(row=0, column=2, padx=(10, 14), pady=12, sticky="ns")
        self.send_btn = ctk.CTkButton(
            right,
            text="Send",
            width=90,
            height=42,
            fg_color=PURPLE,
            hover_color=PURPLE_HOV,
            corner_radius=18,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=0, pady=(22, 14))

        self.model_var = tk.StringVar(value=self.model_name)
        ctk.CTkOptionMenu(
            right,
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
            height=36,
            corner_radius=12,
            fg_color=CARD,
            button_color=BORDER2,
            button_hover_color=PURPLE_DIM,
            text_color=TEXT2,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.change_model,
        ).grid(row=1, column=0)

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, height=34, fg_color=SURFACE, corner_radius=0)
        bar.grid(row=2, column=1, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        self._status_lbl = ctk.CTkLabel(
            bar,
            text=f"  {self.provider_name} · {self.model_name}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
            anchor="w",
        )
        self._status_lbl.grid(row=0, column=0, sticky="w", padx=10)

        center = ctk.CTkLabel(
            bar,
            text="Ctrl+N New · Ctrl+P Prompts · Ctrl+, Settings · Esc Interrupt",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=TEXT3,
            anchor="center",
        )
        center.grid(row=0, column=1, sticky="ew")

        self._token_lbl = ctk.CTkLabel(
            bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT3,
            anchor="e",
        )
        self._token_lbl.grid(row=0, column=2, sticky="e", padx=10)

    def change_model(self, model: str):
        super().change_model(model)
        self._provider_lbl.configure(text=f"  {self.provider_name}  ")
        self._apply_shell_metrics()

    def _finish_processing(self):
        super()._finish_processing()
        self._provider_lbl.configure(text=f"  {self.provider_name}  ")
        self._apply_shell_metrics()

    def new_chat(self):
        super().new_chat()
        self._apply_shell_metrics()

    def load_session(self, filename: str):
        super().load_session(filename)
        self._apply_shell_metrics()


def main():
    from workers import get_pool

    ensure_gui_runtime()
    app = DanModernGUI()
    app.mainloop()
    get_pool().shutdown()


if __name__ == "__main__":
    main()
