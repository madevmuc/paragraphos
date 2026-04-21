"""Theme plumbing for Paragraphos — light/dark following macOS system.

Usage:
    from ui.themes import install_manager, manager, load_qss, tokens

    # In app bootstrap, right after QApplication is created:
    qapp = QApplication(sys.argv)
    tm = install_manager(qapp)

    # In a custom-paint widget:
    tm = manager()
    tm.themeChanged.connect(self.update)
    # in paintEvent:
    t = tm.tokens()

Design notes
------------
- One template (`app.qss.tmpl`) shared between both modes; `load_qss`
  reads it fresh on every apply so the active QSS is always in sync
  with the active dict. Cheap for the size of file this is.
- ThemeManager subscribes to `QGuiApplication.styleHints().colorSchemeChanged`
  (Qt 6.5+). Each callback re-applies QSS AND emits `themeChanged` so
  custom-paint widgets can schedule a repaint.
- A process-wide singleton (`manager()`) keeps widget ctor signatures
  clean — no need to plumb the manager through every subtree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from ui.themes.tokens import DARK, LIGHT, tokens_for

_TEMPLATE_PATH = Path(__file__).resolve().parent / "app.qss.tmpl"
_TEMPLATE_CACHE: Optional[str] = None


def _template() -> str:
    """Read the QSS template once, cache it."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        _TEMPLATE_CACHE = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


def load_qss(mode: str) -> str:
    """Render the QSS template for the given mode.

    Raises KeyError if the template references a token the dict lacks —
    this is intentional; drift between template + tokens should fail
    loud rather than silently leave placeholders in the stylesheet.
    """
    return _template().format_map(tokens_for(mode))


def tokens(mode: str) -> dict[str, str]:
    """Re-export for convenience — returns the LIGHT/DARK dict."""
    return tokens_for(mode)


def current_tokens() -> dict[str, str]:
    """Return the active theme's token dict.

    Shared accessor for every UI module that needs to paint semantic colors
    (danger/warn/ok/accent) without going through QSS. Falls back to LIGHT
    if the ThemeManager has not been installed yet — e.g. during unit tests
    that spin up a widget without booting the full app.
    """
    tm = _manager
    if tm is not None:
        try:
            return tm.tokens()
        except Exception:
            pass
    return LIGHT


class ThemeManager(QObject):
    """Follows macOS system appearance; re-applies QSS on change.

    Emits `themeChanged("light" | "dark")` AFTER the QSS is applied so
    subscribers can rely on the global stylesheet already being fresh.
    """

    themeChanged = pyqtSignal(str)

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app
        self._scheme = self._detect_scheme()
        # Qt 6.5+: connect to the live signal. If this attribute is
        # missing on an older Qt, we silently fall back to "whatever
        # the startup scheme was" — no live updates, but at least
        # the app paints correctly at launch.
        hints = QGuiApplication.styleHints()
        sig = getattr(hints, "colorSchemeChanged", None)
        if sig is not None:
            try:
                sig.connect(self._on_scheme_changed)
            except Exception:
                pass
        self._apply(self._scheme)

    # Public API -----------------------------------------------------

    def scheme(self) -> str:
        """Return the current mode: 'light' or 'dark'."""
        return self._scheme

    def tokens(self) -> dict[str, str]:
        """Return the token dict for the current mode."""
        return DARK if self._scheme == "dark" else LIGHT

    # Internals ------------------------------------------------------

    def _detect_scheme(self) -> str:
        cs = QGuiApplication.styleHints().colorScheme()
        return "dark" if cs == Qt.ColorScheme.Dark else "light"

    def _on_scheme_changed(self, _scheme) -> None:
        new = self._detect_scheme()
        if new == self._scheme:
            return
        self._apply(new)

    def _apply(self, mode: str) -> None:
        self._scheme = mode
        try:
            self._app.setStyleSheet(load_qss(mode))
        except Exception:
            # A KeyError here would swallow the app's first paint —
            # fall back to empty QSS so the user at least sees
            # something while we investigate in logs.
            import traceback

            traceback.print_exc()
            self._app.setStyleSheet("")
        self.themeChanged.emit(mode)


# Module-level singleton. Widgets read it via `manager()`; app
# bootstrap calls `install_manager(qapp)` exactly once.
_manager: Optional[ThemeManager] = None


def install_manager(app) -> ThemeManager:
    """Create and install the process-wide ThemeManager. Idempotent."""
    global _manager
    if _manager is None:
        _manager = ThemeManager(app)
    return _manager


def manager() -> Optional[ThemeManager]:
    """Return the installed ThemeManager, or None if not yet installed.

    Widgets should handle the None case gracefully — during unit tests
    we sometimes instantiate a widget without booting the full app.
    """
    return _manager


__all__ = [
    "ThemeManager",
    "LIGHT",
    "DARK",
    "load_qss",
    "tokens",
    "current_tokens",
    "install_manager",
    "manager",
]
