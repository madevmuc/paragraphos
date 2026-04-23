"""User-resizable, persisted table-column widths.

A tiny helper invoked once from each table tab. Columns become
Interactive (the user can drag the borders); widths are saved to
QSettings on resize and restored on next construction. Right-clicking
the header reveals a single "Reset columns" action that drops the
saved widths and applies the supplied defaults.

`stretch_col` (optional) keeps one column on Stretch so it absorbs the
table's spare horizontal space — typically the title column. `fixed_cols`
pins specific columns to a fixed width (used by the Queue tab's Status
column where the live "transcribing · NN%" text would jitter under any
content-driven resize policy).
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtWidgets import QHeaderView, QMenu


def make_resizable(
    table,
    *,
    settings_key: str,
    stretch_col: int | None = None,
    fixed_cols: dict[int, int] | None = None,
    defaults: dict[int, int] | None = None,
) -> None:
    """Configure ``table``'s columns for user-resize + persistence.

    See module docstring for behavioural detail. Safe to call once during
    table construction.
    """

    fixed_cols = fixed_cols or {}
    defaults = defaults or {}
    header: QHeaderView = table.horizontalHeader()
    n_cols = header.count()

    # Per-column resize mode.
    for col in range(n_cols):
        if col == stretch_col:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        elif col in fixed_cols:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(col, fixed_cols[col])
        else:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

    # Restore widths from QSettings (JSON for forward-compat — Qt's
    # QVariant serialisation of dicts varies across platforms).
    qs = QSettings()
    raw = qs.value(settings_key, "")
    saved: dict[int, int] = {}
    if raw:
        try:
            saved = {int(k): int(v) for k, v in json.loads(raw).items()}
        except Exception:
            saved = {}
    for col in range(n_cols):
        if col == stretch_col or col in fixed_cols:
            continue
        if col in saved:
            table.setColumnWidth(col, saved[col])
        elif col in defaults:
            table.setColumnWidth(col, defaults[col])

    # Debounced save — coalesces a flurry of sectionResized events from a
    # single drag into one QSettings write.
    save_timer = QTimer(table)
    save_timer.setSingleShot(True)
    save_timer.setInterval(300)

    def _persist():
        out: dict[str, int] = {}
        for col in range(n_cols):
            if col == stretch_col:
                # Stretch columns have no persistent width; recomputed on layout.
                continue
            out[str(col)] = int(table.columnWidth(col))
        QSettings().setValue(settings_key, json.dumps(out))

    save_timer.timeout.connect(_persist)
    header.sectionResized.connect(lambda *_: save_timer.start())

    # Context menu — Reset columns.
    def _on_header_menu(pos):
        menu = QMenu(table)
        reset = menu.addAction("Reset columns")
        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen is reset:
            QSettings().remove(settings_key)
            for col, w in defaults.items():
                if col == stretch_col or col in fixed_cols:
                    continue
                table.setColumnWidth(col, w)

    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    header.customContextMenuRequested.connect(_on_header_menu)
