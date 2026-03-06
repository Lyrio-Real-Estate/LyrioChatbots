"""
Compatibility helpers for Streamlit Material icon tokens.

Many dashboard strings use the ``:material/icon_name:`` token style. In some
environments these render as raw text, so this module provides a deterministic
fallback to neutral monochrome symbols.
"""
from __future__ import annotations

import re
from typing import Any

_MATERIAL_TOKEN_PATTERN = re.compile(r":material/([a-z0-9_]+):")

_MATERIAL_TO_SYMBOL: dict[str, str] = {
    "accessibility": "A11Y",
    "ac_unit": "◌",
    "add_circle": "+",
    "arrow_forward": "→",
    "attach_money": "$",
    "bar_chart": "▦",
    "block": "✕",
    "bolt": "ϟ",
    "build": "⌘",
    "calendar_month": "◷",
    "call": "☎",
    "cancel": "✕",
    "check_circle": "✓",
    "chevron_left": "‹",
    "chevron_right": "›",
    "circle": "•",
    "dark_mode": "◐",
    "desktop_windows": "▣",
    "device_thermostat": "°",
    "diamond": "◇",
    "directions_car": "⇢",
    "download": "↓",
    "error": "✕",
    "explore": "◇",
    "forum": "◍",
    "groups": "◎",
    "help": "?",
    "home": "⌂",
    "hourglass_top": "⌛",
    "insights": "◈",
    "light_mode": "○",
    "link": "⛓",
    "local_fire_department": "◆",
    "lock": "⌁",
    "mail": "✉",
    "notifications": "◉",
    "palette": "◧",
    "pause_circle": "‖",
    "payments": "$",
    "person": "◉",
    "phone": "☎",
    "play_arrow": "▶",
    "psychology": "◈",
    "public": "◎",
    "radio_button_unchecked": "○",
    "real_estate_agent": "⌂",
    "receipt_long": "▤",
    "refresh": "↻",
    "report": "!",
    "rocket_launch": "➤",
    "rss_feed": "⌁",
    "schedule": "◷",
    "search": "⌕",
    "settings": "⚙",
    "shield": "◈",
    "smartphone": "▣",
    "sports_esports": "◍",
    "table_chart": "▤",
    "target": "◎",
    "timer": "◴",
    "trending_down": "↘",
    "trending_up": "↗",
    "view_module": "▦",
    "visibility": "◌",
    "warning": "!",
    "wifi_off": "⊘",
    "work": "▧",
}

_NATIVE_MATERIAL_SUPPORT = False


def _detect_native_material_support() -> bool:
    """Check if the installed Streamlit natively renders :material/...: tokens."""
    try:
        import streamlit as st

        raw_version = str(getattr(st, "__version__", "0.0.0"))
        major_minor = raw_version.split(".", 2)[:2]
        major = int(major_minor[0]) if major_minor else 0
        minor = int(major_minor[1]) if len(major_minor) > 1 else 0
        # Material symbol token support arrived in newer Streamlit builds.
        return (major, minor) >= (1, 40)
    except Exception:
        return False


_NATIVE_MATERIAL_SUPPORT = _detect_native_material_support()


def icon_text(value: Any) -> Any:
    """
    Replace ``:material/...:`` tokens with neutral fallback symbols.

    Supports strings, lists, tuples and dictionaries recursively. Other value
    types are returned unchanged.
    """
    if _NATIVE_MATERIAL_SUPPORT:
        return value
    if isinstance(value, str):
        return _MATERIAL_TOKEN_PATTERN.sub(_replace_material_token, value)
    if isinstance(value, list):
        return [icon_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(icon_text(item) for item in value)
    if isinstance(value, dict):
        return {key: icon_text(item) for key, item in value.items()}
    return value


def _replace_material_token(match: re.Match[str]) -> str:
    icon_name = match.group(1)
    return _MATERIAL_TO_SYMBOL.get(icon_name, "•")
