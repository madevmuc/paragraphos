"""Design tokens for the Phase 6 refresh.

Referenced by every widget in `ui/widgets/` — no hard-coded spacing
or font sizes elsewhere. Single `apply_app_qss(app)` call installs the
global stylesheet at startup.

Palette strategy: stick with native macOS `palette()` roles where
possible; introduce one accent color (`#b47a3a` ochre/clay) only for
primary buttons, selected rows, and progress fills.
"""

from __future__ import annotations

TOKENS = {
    # Spacing scale — the only allowed values
    "space": {"xs": 4, "sm": 6, "md": 8, "lg": 10, "xl": 12, "xxl": 14, "huge": 18},

    # Radii
    "radius_sm": 5,   # pills, inputs
    "radius_md": 9,   # cards, dialogs

    # Font sizes
    "font_tiny": 10,    # uppercase mini-labels
    "font_small": 11,   # muted hints
    "font_body": 12,    # table cells, caption
    "font_base": 13,    # standard body
    "font_heading": 14, # section headers, dialog titles

    # Colors — only place hard-coded hex lives in the codebase
    "accent": "#b47a3a",
    "accent_tint": "rgba(180, 122, 58, 0.12)",
    "danger": "#b04040",
    "ok": "#4a7a44",

    # Mono font family for numbers, slugs, timestamps, paths
    "mono_family": "Menlo, Monaco, 'SF Mono', monospace",
}


_APP_QSS = f"""
QLabel#Pill {{
    padding: 2px 8px;
    border-radius: {TOKENS['radius_sm']}px;
    font-size: {TOKENS['font_small']}px;
    font-weight: 500;
    background: palette(alternate-base);
    color: palette(mid);
}}
QLabel#Pill[kind="ok"]       {{ background: {TOKENS['accent_tint']}; color: {TOKENS['accent']}; }}
QLabel#Pill[kind="running"]  {{ background: {TOKENS['accent']};      color: white; }}
QLabel#Pill[kind="fail"]     {{ background: rgba(176, 64, 64, 0.15); color: {TOKENS['danger']}; }}
QLabel#Pill[kind="idle"]     {{ background: palette(alternate-base); color: palette(mid); }}

QLabel.mini-label {{
    font-size: {TOKENS['font_tiny']}px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: palette(mid);
    text-transform: uppercase;
}}
QLabel.mono {{
    font-family: {TOKENS['mono_family']};
}}
QLabel.muted {{
    color: palette(mid);
}}
QLabel.heading {{
    font-size: {TOKENS['font_heading']}px;
    font-weight: 600;
}}

QPushButton[role="primary"] {{
    background: {TOKENS['accent']};
    color: white;
    border: 1px solid {TOKENS['accent']};
    border-radius: {TOKENS['radius_sm']}px;
    padding: 4px 12px;
    font-weight: 600;
}}
QPushButton[role="ghost"] {{
    background: transparent;
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: {TOKENS['radius_sm']}px;
    padding: 4px 12px;
}}

#Sidebar {{
    background: palette(alternate-base);
    border-right: 1px solid palette(mid);
}}
#SidebarItem {{
    padding: 6px 10px;
    border-radius: {TOKENS['radius_sm']}px;
}}
#SidebarItem[active="true"] {{
    background: {TOKENS['accent_tint']};
    color: palette(text);
    font-weight: 500;
}}
#SidebarItem QLabel.count {{
    font-family: {TOKENS['mono_family']};
    font-size: {TOKENS['font_small']}px;
    color: palette(mid);
}}
"""


def apply_app_qss(app) -> None:
    """Install the token-derived stylesheet on the QApplication."""
    existing = app.styleSheet() or ""
    app.setStyleSheet(existing + "\n" + _APP_QSS)
