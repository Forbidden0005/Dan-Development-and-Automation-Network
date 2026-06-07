"""Theme tokens for the Dan desktop GUI."""

from __future__ import annotations

from dataclasses import dataclass


THEME_DARK = "dark"
THEME_LIGHT = "light"
VALID_THEMES = {THEME_DARK, THEME_LIGHT}


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    appearance_mode: str
    background: str
    sidebar: str
    sidebar_alt: str
    main: str
    surface: str
    surface_alt: str
    surface_hover: str
    selected: str
    input_bg: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    success: str
    warning: str
    error: str
    user_bubble: str
    user_text: str
    assistant_bubble: str
    tool_text: str
    disabled: str


THEMES = {
    THEME_DARK: ThemeTokens(
        name=THEME_DARK,
        appearance_mode="dark",
        background="#15110d",
        sidebar="#1d1712",
        sidebar_alt="#251d17",
        main="#17130f",
        surface="#211a14",
        surface_alt="#2a211a",
        surface_hover="#332821",
        selected="#3a2b21",
        input_bg="#120f0c",
        border="#3b3028",
        border_strong="#574538",
        text="#f3eee7",
        text_muted="#c7b9aa",
        text_subtle="#8f8173",
        accent="#c35a32",
        accent_hover="#d66a3e",
        accent_soft="#4d2418",
        accent_text="#fff7ef",
        success="#48b36a",
        warning="#d59a3a",
        error="#df665f",
        user_bubble="#3a2b21",
        user_text="#f4ede4",
        assistant_bubble="#211a14",
        tool_text="#b79070",
        disabled="#695b4f",
    ),
    THEME_LIGHT: ThemeTokens(
        name=THEME_LIGHT,
        appearance_mode="light",
        background="#f6f1e9",
        sidebar="#eee7dc",
        sidebar_alt="#f7f1e8",
        main="#fbf7f0",
        surface="#fffaf3",
        surface_alt="#f2eadf",
        surface_hover="#eadfd1",
        selected="#e8d9ca",
        input_bg="#fffdf8",
        border="#d8cbbd",
        border_strong="#bda998",
        text="#2e2924",
        text_muted="#695e53",
        text_subtle="#8e8174",
        accent="#c35a32",
        accent_hover="#ad4c29",
        accent_soft="#f0d5c8",
        accent_text="#fff8f1",
        success="#2f9e57",
        warning="#b7791f",
        error="#c94a43",
        user_bubble="#efe2d4",
        user_text="#2e2924",
        assistant_bubble="#fffaf3",
        tool_text="#8f5a3d",
        disabled="#9b8d80",
    ),
}


def normalize_theme(value) -> str:
    """Return a supported theme name, defaulting safely to dark."""
    if not isinstance(value, str):
        return THEME_DARK
    normalized = value.strip().lower()
    return normalized if normalized in VALID_THEMES else THEME_DARK


def theme_from_config(config: dict) -> str:
    """Read the UI theme from config with a defensive dark fallback."""
    ui_config = config.get("ui", {}) if isinstance(config, dict) else {}
    theme_value = ui_config.get("theme") if isinstance(ui_config, dict) else None
    return normalize_theme(theme_value)


def get_theme_tokens(value) -> ThemeTokens:
    """Return immutable tokens for a supported theme name."""
    return THEMES[normalize_theme(value)]
