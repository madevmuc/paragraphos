"""Compatibility shim — design tokens moved to ui.themes.

Kept alive so existing call-sites (`from ui.widgets import TOKENS,
apply_app_qss`) keep working after the dark-mode refresh. The real
source of truth is now `ui/themes/tokens.py` + `ui/themes/app.qss.tmpl`,
rendered at runtime by `ui.themes.ThemeManager` per system appearance.
"""

from __future__ import annotations

from ui.themes import install_manager
from ui.themes.tokens import LIGHT

# TOKENS retained for any call-site that still reads numeric spacing
# or font-size constants. Color keys here now mirror the LIGHT theme;
# runtime color handling goes through ThemeManager.
TOKENS = {
    # Spacing scale — the only allowed values
    "space": {"xs": 4, "sm": 6, "md": 8, "lg": 10, "xl": 12, "xxl": 14, "huge": 18},
    # Radii
    "radius_sm": 5,
    "radius_md": 9,
    # Font sizes
    "font_tiny": 10,
    "font_small": 11,
    "font_body": 12,
    "font_base": 13,
    "font_heading": 14,
    # Colors — compat aliases pointing at the LIGHT dict. Prefer
    # reading from `ui.themes.manager().tokens()` in new code.
    "accent": LIGHT["accent"],
    "accent_tint": LIGHT["accent_tint"],
    "danger": LIGHT["danger"],
    "ok": LIGHT["ok"],
    # Mono font family for numbers, slugs, timestamps, paths
    "mono_family": "Menlo, Monaco, 'SF Mono', monospace",
}


def apply_app_qss(app) -> None:
    """Install the ThemeManager (which renders + applies the QSS).

    Legacy name; prefer `ui.themes.install_manager(app)` in new code.
    Idempotent — subsequent calls return the existing manager.
    """
    install_manager(app)
