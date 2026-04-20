"""Reusable UI widgets introduced by the Phase 6 design refresh.

Exports:
    - apply_app_qss, TOKENS
    - Pill
    - Sidebar
    - FilterPopover
    - ProgressRing
    - IconRenderer
"""

from ui.widgets._tokens import TOKENS, apply_app_qss
from ui.widgets.filter_popover import FilterPopover
from ui.widgets.pill import Pill
from ui.widgets.progress_ring import ProgressRing
from ui.widgets.sidebar import Sidebar
from ui.widgets.tray_icon_renderer import IconRenderer


def __getattr__(name):
    # Lazy export so `from ui.widgets import QueueHero` works without
    # creating an import cycle with queue_hero, which imports from ui.widgets.
    if name == "QueueHero":
        from ui.widgets.queue_hero import QueueHero
        return QueueHero
    raise AttributeError(name)


__all__ = [
    "TOKENS", "apply_app_qss",
    "Pill", "Sidebar", "FilterPopover", "ProgressRing", "IconRenderer",
    "QueueHero",
]
