"""Settings pane — auto-saves on every change, grouped by theme."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTime, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

_MODEL_DIR = Path.home() / ".config" / "open-wispr" / "models"


def _model_installed(name: str) -> bool:
    return (_MODEL_DIR / f"ggml-{name}.bin").exists()


def _section(title: str) -> QLabel:
    lbl = QLabel(f"<b>{title}</b>")
    lbl.setStyleSheet(
        "padding:10px 0 4px 0; color:palette(mid); "
        "border-bottom:1px solid palette(mid); margin-top:8px;"
    )
    return lbl


class SettingsPane(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        # Everything below lives inside a scrollable container so the pane
        # works at any window height.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)

        # ── Library & output ───────────────────────────────────
        root.addWidget(_section("Library & output"))
        f1 = QFormLayout()
        self.output = QLineEdit(self.ctx.settings.output_root)
        self.output.textChanged.connect(self._schedule_save)
        pick_row = QHBoxLayout()
        pick_row.addWidget(self.output)
        pick = QPushButton("Browse…")
        pick.clicked.connect(self._pick_dir)
        pick_row.addWidget(pick)
        self._add_field(
            f1,
            "Output root",
            self._row_widget(pick_row),
            hint="markdown transcripts land here, one folder per show",
            hint_kind="info",
        )

        self.export_root = QLineEdit(self.ctx.settings.export_root)
        self.export_root.textChanged.connect(self._schedule_save)
        exp_row = QHBoxLayout()
        exp_row.addWidget(self.export_root)
        exp_pick = QPushButton("Browse…")
        exp_pick.clicked.connect(self._pick_export)
        exp_row.addWidget(exp_pick)
        self._add_field(f1, "Export ZIP target", self._row_widget(exp_row))

        self.obsidian_path = QLineEdit(self.ctx.settings.obsidian_vault_path)
        self.obsidian_path.textChanged.connect(self._schedule_save)
        obs_row = QHBoxLayout()
        obs_row.addWidget(self.obsidian_path)
        obs_pick = QPushButton("Browse…")
        obs_pick.clicked.connect(self._pick_obsidian)
        obs_row.addWidget(obs_pick)
        self._add_field(
            f1,
            "Obsidian vault path",
            self._row_widget(obs_row),
            hint='auto-fills vault name from folder ("wiki")',
            hint_kind="info",
        )

        self.obsidian_name = QLineEdit(self.ctx.settings.obsidian_vault_name)
        self.obsidian_name.textChanged.connect(self._schedule_save)
        self._add_field(f1, "Obsidian vault name", self.obsidian_name)

        self.kb_root = QLineEdit(self.ctx.settings.knowledge_hub_root)
        self.kb_root.textChanged.connect(self._schedule_save)
        kb_row = QHBoxLayout()
        kb_row.addWidget(self.kb_root)
        kb_pick = QPushButton("Browse…")
        kb_pick.clicked.connect(self._pick_kb_root)
        kb_row.addWidget(kb_pick)
        kb_hint, kb_kind = self._kb_root_hint(self.kb_root.text())
        self._add_field(
            f1,
            "Knowledge-hub root (optional)",
            self._row_widget(kb_row),
            hint=kb_hint,
            hint_kind=kb_kind,
        )
        root.addLayout(f1)

        # ── Schedule & monitoring ──────────────────────────────
        root.addWidget(_section("Schedule & monitoring"))
        f2 = QFormLayout()
        self.time = QTimeEdit(QTime.fromString(self.ctx.settings.daily_check_time, "HH:mm"))
        self.time.timeChanged.connect(self._schedule_save)
        self._add_field(
            f2,
            "Daily check time",
            self.time,
            hint="runs in the background — Mac must be awake",
            hint_kind="info",
        )
        self.catchup = QCheckBox()
        self.catchup.setChecked(self.ctx.settings.catch_up_missed)
        self.catchup.stateChanged.connect(self._schedule_save)
        self._add_field(
            f2,
            "Catch-up missed runs",
            self.catchup,
            hint="recommended — runs immediately on wake if a check was missed",
            hint_kind="good",
        )
        root.addLayout(f2)

        # ── Notifications ──────────────────────────────────────
        root.addWidget(_section("Notifications"))
        f3 = QFormLayout()
        self.notify = QCheckBox()
        self.notify.setChecked(self.ctx.settings.notify_on_success)
        self.notify.stateChanged.connect(self._schedule_save)
        notify_row = QHBoxLayout()
        notify_row.addWidget(self.notify)
        sys_btn = QPushButton("Open macOS Notification settings…")
        sys_btn.clicked.connect(self._open_notification_prefs)
        notify_row.addWidget(sys_btn)
        notify_row.addStretch()
        self._add_field(
            f3,
            "Notify on successful transcription",
            self._row_widget(notify_row),
            hint="if silent: re-enable in macOS → Notifications",
            hint_kind="info",
        )

        self.notify_mode = QComboBox()
        for label, code in (
            ("Per-episode", "per_episode"),
            ("Daily summary (one message per run)", "daily_summary"),
            ("Off", "off"),
        ):
            self.notify_mode.addItem(label, code)
        idx = next(
            (
                i
                for i in range(self.notify_mode.count())
                if self.notify_mode.itemData(i) == self.ctx.settings.notify_mode
            ),
            0,
        )
        self.notify_mode.setCurrentIndex(idx)
        self.notify_mode.currentIndexChanged.connect(self._schedule_save)
        self._add_field(f3, "Notification frequency", self.notify_mode)
        root.addLayout(f3)

        # ── Transcription engine ───────────────────────────────
        root.addWidget(_section("Transcription engine"))
        f4 = QFormLayout()
        model_row = QHBoxLayout()
        self.model = QComboBox()
        for m in ("base", "small", "medium", "large-v3", "large-v3-turbo"):
            self.model.addItem(m)
        self.model.setCurrentText(self.ctx.settings.whisper_model)
        self.model.currentTextChanged.connect(self._on_model_changed)
        model_row.addWidget(self.model)
        self.model_status = QLabel()
        self.model_status.setStyleSheet("color: #888; font-style: italic;")
        model_row.addWidget(self.model_status, stretch=1)
        self._add_field(
            f4,
            "Whisper model",
            self._row_widget(model_row),
            hint="best accuracy/speed balance on Apple Silicon — recommended",
            hint_kind="good",
        )
        self._update_model_status()

        rec_n = self._hw_recommendation_value()
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 4)
        # Seed from settings if set; otherwise use the hardware recommendation.
        self.parallel.setValue(self.ctx.settings.parallel_transcribe or rec_n)
        self.parallel.valueChanged.connect(self._schedule_save)
        self._add_field(
            f4,
            "Parallel workers",
            self.parallel,
            hint=f"recommended: {self._hw_recommendation_hint()}",
            hint_kind="good",
        )

        self.bw = QSpinBox()
        self.bw.setRange(0, 1000)
        self.bw.setValue(self.ctx.settings.bandwidth_limit_mbps)
        self.bw.valueChanged.connect(self._schedule_save)
        self._add_field(
            f4,
            "Bandwidth limit (Mbps, 0=∞)",
            self.bw,
            hint="0 = unlimited. Try 20 Mbps if shared Wi-Fi starts hitching",
            hint_kind="info",
        )

        self.fast_mode = QCheckBox("Fast mode (less accurate, ~2–3× faster)")
        self.fast_mode.setChecked(self.ctx.settings.whisper_fast_mode)
        self.fast_mode.stateChanged.connect(self._schedule_save)
        self._add_field(f4, "Whisper speed", self.fast_mode)

        self.multiproc = QSpinBox()
        self.multiproc.setRange(1, 8)
        self.multiproc.setValue(self.ctx.settings.whisper_multiproc)
        self.multiproc.valueChanged.connect(self._schedule_save)
        self._add_field(
            f4,
            "Multi-processor split",
            self.multiproc,
            hint="whisper-cli -p N splits audio across N cores "
            "(1 = disabled, 4 recommended for long episodes)",
            hint_kind="info",
        )

        root.addLayout(f4)

        # ── Storage & retention ────────────────────────────────
        root.addWidget(_section("Storage & retention"))
        f5 = QFormLayout()
        self.retention = QSpinBox()
        self.retention.setRange(0, 365)
        self.retention.setValue(self.ctx.settings.mp3_retention_days)
        self.retention.valueChanged.connect(self._schedule_save)
        self._add_field(
            f5,
            "MP3 retention (days)",
            self.retention,
            hint="transcripts are kept forever — only the audio is purged",
            hint_kind="info",
        )
        self.del_mp3 = QCheckBox()
        self.del_mp3.setChecked(self.ctx.settings.delete_mp3_after_transcribe)
        self.del_mp3.stateChanged.connect(self._schedule_save)
        self._add_field(
            f5,
            "Delete MP3 after transcribe",
            self.del_mp3,
            hint="turn on to save ~40 GB/yr if you never re-play audio",
            hint_kind="info",
        )
        self.log_retention = QSpinBox()
        self.log_retention.setRange(1, 365)
        self.log_retention.setValue(self.ctx.settings.log_retention_days)
        self.log_retention.valueChanged.connect(self._schedule_save)
        self._add_field(
            f5,
            "Log retention (days)",
            self.log_retention,
            hint="enough to debug any failed run",
            hint_kind="info",
        )
        root.addLayout(f5)

        # ── Save indicator ─────────────────────────────────────
        self._saved_label = QLabel("")
        self._saved_label.setStyleSheet("color: #5a8a4a; font-size: 11px;")
        root.addWidget(self._saved_label)

        # ── Automation & remote control ────────────────────────
        root.addWidget(_section("Automation & remote control"))
        help_text = QLabel(self._terminal_help_html())
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_text.setWordWrap(True)
        help_text.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
        root.addWidget(help_text)

        root.addWidget(
            QLabel(
                "<br><b>Example prompt for an AI agent (Claude Code, Gemini CLI, etc.)</b> — "
                "paste after giving the agent shell access to this directory:"
            )
        )
        agent_prompt = QLabel(self._agent_prompt_html())
        agent_prompt.setTextFormat(Qt.TextFormat.RichText)
        agent_prompt.setWordWrap(True)
        agent_prompt.setStyleSheet(
            "background: palette(alternate-base); padding: 10px; "
            "border: 1px solid palette(mid); border-radius: 4px; "
            "font-family: Menlo, Monaco, monospace; font-size: 11px; "
            "white-space: pre-wrap;"
        )
        agent_prompt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(agent_prompt)

        copy_btn = QPushButton("Copy agent prompt to clipboard")
        copy_btn.clicked.connect(self._copy_agent_prompt)
        root.addWidget(copy_btn)

        root.addStretch()

    # ── actions ───────────────────────────────────────────────

    def _pick_dir(self):
        start = str(Path(self.output.text()).expanduser())
        d = QFileDialog.getExistingDirectory(self, "Pick output root", start)
        if d:
            self.output.setText(d)

    def _pick_kb_root(self):
        start = str(Path(self.kb_root.text() or "~").expanduser())
        d = QFileDialog.getExistingDirectory(self, "Pick knowledge-hub root", start)
        if d:
            self.kb_root.setText(d)

    def _pick_obsidian(self):
        start = str(Path(self.obsidian_path.text()).expanduser())
        d = QFileDialog.getExistingDirectory(self, "Pick Obsidian vault", start)
        if d:
            self.obsidian_path.setText(d)
            self.obsidian_name.setText(Path(d).name)

    def _pick_export(self):
        start = str(Path(self.export_root.text()).expanduser())
        d = QFileDialog.getExistingDirectory(self, "Pick export root", start)
        if d:
            self.export_root.setText(d)

    def _open_notification_prefs(self):
        import subprocess

        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.notifications"])

    def _copy_agent_prompt(self):
        from PyQt6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._agent_prompt_plain())

    def _on_model_changed(self, text: str) -> None:
        self._schedule_save()
        self._update_model_status()
        if not _model_installed(text):
            self._download_model(text)

    def _update_model_status(self) -> None:
        name = self.model.currentText()
        if _model_installed(name):
            self.model_status.setText("● installed")
            self.model_status.setStyleSheet("color: #5a8a4a; font-style: normal;")
        else:
            self.model_status.setText("○ not installed — will download on next use")
            self.model_status.setStyleSheet("color: #a06030; font-style: italic;")

    def _download_model(self, name: str) -> None:
        from core.model_download import download_model_async

        self.model_status.setText("⏳ downloading…")
        self.model_status.setStyleSheet("color: #606090;")

        def on_done(ok: bool, err: str):
            if ok:
                self._update_model_status()
            else:
                self.model_status.setText(f"✖ {err}")
                self.model_status.setStyleSheet("color: #a04040;")

        download_model_async(name, on_done)

    def _schedule_save(self):
        self._saved_label.setText("…")
        self._save_timer.start(250)

    def _do_save(self):
        s = self.ctx.settings
        s.output_root = self.output.text()
        s.daily_check_time = self.time.time().toString("HH:mm")
        s.catch_up_missed = self.catchup.isChecked()
        s.notify_on_success = self.notify.isChecked()
        s.mp3_retention_days = self.retention.value()
        s.delete_mp3_after_transcribe = self.del_mp3.isChecked()
        s.bandwidth_limit_mbps = self.bw.value()
        s.parallel_transcribe = self.parallel.value()
        s.obsidian_vault_path = self.obsidian_path.text()
        s.obsidian_vault_name = self.obsidian_name.text()
        s.knowledge_hub_root = self.kb_root.text()
        s.export_root = self.export_root.text()
        s.whisper_model = self.model.currentText()
        s.whisper_fast_mode = self.fast_mode.isChecked()
        s.whisper_multiproc = self.multiproc.value()
        s.notify_mode = self.notify_mode.currentData() or "per_episode"
        s.log_retention_days = self.log_retention.value()
        s.save(self.ctx.data_dir / "settings.yaml")
        from datetime import datetime

        self._saved_label.setText(f"✓ saved at {datetime.now().strftime('%H:%M:%S')}")
        self.ctx.reload_library()

    def refresh(self) -> None:
        s = self.ctx.settings
        self.output.blockSignals(True)
        self.output.setText(s.output_root)
        self.output.blockSignals(False)
        self.time.blockSignals(True)
        self.time.setTime(QTime.fromString(s.daily_check_time, "HH:mm"))
        self.time.blockSignals(False)

    # ── field helper ──────────────────────────────────────────

    def _add_field(self, form, label, widget, hint=None, hint_kind="info"):
        """Add a form row with an optional hint line below."""
        if hint is None:
            form.addRow(label, widget)
            return
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(widget)
        prefix = "✓ " if hint_kind == "good" else "ⓘ "
        h = QLabel(prefix + hint)
        h.setWordWrap(True)
        if hint_kind == "good":
            h.setStyleSheet("color: #4a7a44; font-size: 11px;")
        else:
            h.setStyleSheet("color: palette(mid); font-size: 11px; font-style: italic;")
        v.addWidget(h)
        form.addRow(label, container)

    def _row_widget(self, layout) -> QWidget:
        """Wrap an HBox layout in a QWidget so it can be added via _add_field."""
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _kb_root_hint(self, path: str):
        """Return (hint, kind) for the knowledge-hub root field."""
        p = (path or "").strip()
        if not p:
            return ("optional — leave blank if you don't use a knowledge hub", "info")
        expanded = Path(p).expanduser()
        if expanded.exists():
            return (f"detected at {expanded}", "good")
        return ("path does not exist — transcripts will not be mirrored there", "info")

    # ── hint text ─────────────────────────────────────────────

    def _hw_detect(self):
        """Return (mem_gb: float|None, perf_cores: int|None). None on detect failure."""
        import subprocess

        try:
            mem_bytes = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            )
            ncpu = int(
                subprocess.check_output(["sysctl", "-n", "hw.perflevel0.physicalcpu"])
                .decode()
                .strip()
            )
        except Exception:
            return (None, None)
        return (mem_bytes / (1024**3), ncpu)

    def _hw_recommendation_value(self) -> int:
        """Numeric worker count to seed the spinner (1-N)."""
        mem_gb, ncpu = self._hw_detect()
        if mem_gb is None or ncpu is None:
            return 1
        if mem_gb < 16:
            return 1
        if mem_gb <= 32 and ncpu >= 8:
            return 2
        return 3

    def _hw_recommendation_hint(self) -> str:
        """Full hint string: '2 (16 GB RAM, 8 perf cores detected)'."""
        rec = self._hw_recommendation_value()
        mem_gb, ncpu = self._hw_detect()
        if mem_gb is None or ncpu is None:
            return f"{rec} (auto-detect failed — set conservatively)"
        return f"{rec} ({mem_gb:.0f} GB RAM, {ncpu} perf cores detected)"

    def _hw_recommendation(self) -> str:
        """Back-compat shim: original full-label form."""
        return f"  recommended: {self._hw_recommendation_hint()}"

    def _terminal_help_html(self) -> str:
        return (
            "<b>Terminal commands</b> (headless — same codebase):<br>"
            "&nbsp;• <b>add &lt;name-or-url&gt;</b> — adds a show, seeds episodes as pending<br>"
            "&nbsp;• <b>list</b> — prints the watchlist<br>"
            "&nbsp;• <b>check [--show &lt;slug&gt;] [--limit N]</b> — full pipeline<br>"
            "&nbsp;• <b>import-feeds</b> — bulk-imports the 16 real-estate feeds<br><br>"
            "Run from <code>scripts/paragraphos/</code>:<br>"
            "<code>PYTHONPATH=. ../../.venv/bin/python cli.py &lt;cmd&gt;</code>"
        )

    def _agent_prompt_plain(self) -> str:
        return (
            "You have shell access to the Paragraphos codebase at\n"
            "  /Users/.../knowledge-hub/scripts/paragraphos/\n"
            "\n"
            "Paragraphos is a local podcast → whisper.cpp transcription pipeline.\n"
            "State (shows, queue, completed episodes) lives in\n"
            "  ~/Library/Application Support/Paragraphos/state.sqlite\n"
            "  ~/Library/Application Support/Paragraphos/watchlist.yaml\n"
            "\n"
            "Use these headless CLI commands via\n"
            "  cd scripts/paragraphos && \\\n"
            "  PYTHONPATH=. ../../.venv/bin/python cli.py <cmd>\n"
            "\n"
            "Commands:\n"
            "  add <name-or-url>         — add a new show by iTunes name or RSS URL\n"
            "  list                      — print the current watchlist\n"
            "  check [--show <slug>] [--limit N]\n"
            "                            — refresh feeds + process pending episodes\n"
            "  import-feeds              — bulk-import the 16 curated real-estate feeds\n"
            "\n"
            "Also query state directly with sqlite:\n"
            "  sqlite3 ~/Library/Application\\ Support/Paragraphos/state.sqlite \\\n"
            '          "SELECT status, COUNT(*) FROM episodes GROUP BY status;"\n'
            "\n"
            "Task: <describe what you want the agent to do, e.g. 'add the podcast X,\n"
            "transcribe the last 5 episodes, then summarize their titles'>.\n"
        )

    def _agent_prompt_html(self) -> str:
        import html

        return html.escape(self._agent_prompt_plain())
