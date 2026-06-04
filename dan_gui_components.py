"""Reusable UI helpers and chat widgets for the Dan GUI."""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk


def popup_base(parent, title: str, width: int, height: int, surface_color: str) -> ctk.CTkToplevel:
    """Create a standard modal popup window."""
    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.geometry(f"{width}x{height}")
    window.configure(fg_color=surface_color)
    window.transient(parent)
    window.grab_set()
    window.after(50, lambda: (window.lift(), window.focus_force()))
    return window


def label(parent, text, text_color: str, size: int = 13, weight: str = "normal", **kwargs):
    """Create a styled CTkLabel."""
    return ctk.CTkLabel(
        parent,
        text=text,
        text_color=text_color,
        font=ctk.CTkFont(family="Segoe UI", size=size, weight=weight),
        **kwargs,
    )


def button(
    parent,
    text,
    command,
    fg_color: str,
    hover_color: str,
    width=None,
    height: int = 36,
    radius: int = 10,
    **kwargs,
):
    """Create a styled CTkButton."""
    props = dict(
        height=height,
        fg_color=fg_color,
        hover_color=hover_color,
        corner_radius=radius,
        font=ctk.CTkFont(family="Segoe UI", size=13),
    )
    props.update(kwargs)
    if width:
        props["width"] = width
    return ctk.CTkButton(parent, text=text, command=command, **props)


class ThinkingDots(ctk.CTkFrame):
    """Animated three-dot status indicator used during generation."""

    _SEQ = [
        ["#9060f5", "#4a1a9e", "#2a0a6e"],
        ["#4a1a9e", "#9060f5", "#4a1a9e"],
        ["#2a0a6e", "#4a1a9e", "#9060f5"],
    ]

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent", height=20)
        self._active = False
        self._step = 0
        self._dots = []
        for i in range(3):
            dot = ctk.CTkLabel(
                self,
                text="o",
                width=14,
                height=14,
                fg_color="transparent",
                font=ctk.CTkFont(size=11),
                text_color=self._SEQ[0][i],
            )
            dot.grid(row=0, column=i, padx=2)
            self._dots.append(dot)

    def start(self):
        self._active = True
        self._tick()

    def stop(self):
        self._active = False

    def _tick(self):
        if not self._active:
            return
        for dot, color in zip(self._dots, self._SEQ[self._step % 3]):
            dot.configure(text_color=color)
        self._step += 1
        self.after(320, self._tick)


class GradientStrip(tk.Canvas):
    """Simple top-edge gradient accent."""

    def __init__(self, parent, color_one: str, color_two: str, height: int = 2, **kwargs):
        super().__init__(parent, height=height, bd=0, highlightthickness=0, **kwargs)
        self._color_one = color_one
        self._color_two = color_two
        self._height = height
        self.bind("<Configure>", self._draw)

    def _draw(self, _=None):
        width = self.winfo_width() or 1
        self.delete("all")
        red_one, green_one, blue_one = self.winfo_rgb(self._color_one)
        red_two, green_two, blue_two = self.winfo_rgb(self._color_two)
        for x in range(width):
            blend = x / width
            red = int((red_one + (red_two - red_one) * blend) / 256)
            green = int((green_one + (green_two - green_one) * blend) / 256)
            blue = int((blue_one + (blue_two - blue_one) * blend) / 256)
            self.create_line(x, 0, x, self._height, fill=f"#{red:02x}{green:02x}{blue:02x}")


class LiveBubble:
    """Streaming assistant bubble that can receive tool lines and text chunks."""

    def __init__(
        self,
        parent,
        *,
        assistant_bg: str,
        border_color: str,
        purple_dim: str,
        card_hover: str,
        text_color: str,
        muted_text_color: str,
        tool_color: str,
    ):
        self._card_hover = card_hover
        self._muted_text_color = muted_text_color

        self.outer = ctk.CTkFrame(parent, fg_color="transparent")
        self.outer.grid(sticky="ew", pady=(0, 4))
        self.outer.grid_columnconfigure(1, weight=1)
        self.outer.grid_columnconfigure(2, minsize=80, weight=0)

        avatar = ctk.CTkFrame(self.outer, width=36, height=36, fg_color=purple_dim, corner_radius=18)
        avatar.grid(row=0, column=0, padx=(0, 10), sticky="n", pady=(4, 0))
        avatar.grid_propagate(False)
        ctk.CTkLabel(
            avatar,
            text="*",
            width=36,
            height=36,
            fg_color="transparent",
            font=ctk.CTkFont(size=16),
            text_color="#c4b5fd",
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.bubble = ctk.CTkFrame(
            self.outer,
            fg_color=assistant_bg,
            corner_radius=14,
            border_width=1,
            border_color=border_color,
        )
        self.bubble.grid(row=0, column=1, sticky="ew")
        self.bubble.grid_columnconfigure(0, weight=1)

        self._dots = ThinkingDots(self.bubble)
        self._dots.grid(row=0, column=0, padx=14, pady=12, sticky="w")
        self._dots.start()

        self.textbox = ctk.CTkTextbox(
            self.bubble,
            fg_color="transparent",
            border_width=0,
            corner_radius=0,
            wrap="word",
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            activate_scrollbars=False,
        )
        self._textbox_widget = self.textbox._textbox
        self._textbox_widget.tag_configure("tool", foreground=tool_color, font=("Segoe UI", 12))
        self._textbox_widget.tag_configure("normal", foreground=text_color, font=("Segoe UI", 14))

        self._streaming = False
        self._has_content = False
        self._full_text = ""

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
        self._dots.stop()
        if not self._has_content and fallback:
            self._ensure_textbox()
            self._full_text = fallback
            self.textbox.configure(state="normal")
            self._textbox_widget.insert("end", fallback, "normal")
            self.textbox.configure(state="disabled")
        self._fit()
        self._add_copy_button()

    def _ensure_textbox(self):
        if not self._has_content:
            self._dots.stop()
            try:
                self._dots.grid_remove()
            except Exception:
                pass
            self._has_content = True
            self.textbox.grid(row=0, column=0, sticky="ew", padx=4, pady=8)

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
                width=44,
                height=24,
                fg_color="transparent",
                hover_color=self._card_hover,
                text_color=self._muted_text_color,
                corner_radius=6,
                font=ctk.CTkFont(size=11),
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
