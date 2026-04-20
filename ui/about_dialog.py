"""About + Changelog dialogs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.version import VERSION

# CHANGELOG.md sits at the Paragraphos repo root, one level above `ui/`.
CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


# (name, version-rough, license-SPDX, project URL)
DEPENDENCIES = [
    ("Python", "3.12", "PSF-2.0", "https://python.org"),
    (
        "Qt / PyQt6",
        "6.6+",
        "GPL-3.0 / Commercial (Riverbank)",
        "https://www.riverbankcomputing.com/software/pyqt/",
    ),
    ("whisper.cpp", "HEAD", "MIT", "https://github.com/ggerganov/whisper.cpp"),
    ("OpenAI Whisper model (large-v3-turbo)", "2024", "MIT", "https://github.com/openai/whisper"),
    ("APScheduler", "3.10+", "MIT", "https://apscheduler.readthedocs.io/"),
    ("watchdog", "4.0+", "Apache-2.0", "https://github.com/gorakhargosh/watchdog"),
    ("feedparser", "6.0+", "BSD-2-Clause", "https://github.com/kurtmckee/feedparser"),
    ("httpx", "0.27+", "BSD-3-Clause", "https://www.python-httpx.org/"),
    ("pydantic", "2.6+", "MIT", "https://docs.pydantic.dev/"),
    ("beautifulsoup4", "4.12+", "MIT", "https://www.crummy.com/software/BeautifulSoup/"),
    ("lxml", "5.0+", "BSD-3-Clause", "https://lxml.de/"),
    ("PyYAML", "6.0+", "MIT", "https://pyyaml.org/"),
    ("ffmpeg", "6+", "LGPL-2.1 / GPL", "https://ffmpeg.org/"),
    ("Homebrew", "4+", "BSD-2-Clause", "https://brew.sh/"),
    ("defusedxml", "0.7+", "PSF-2.0", "https://github.com/tiran/defusedxml"),
]


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Paragraphos")
        self.resize(720, 560)
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._about_tab(), "About")
        tabs.addTab(self._licenses_tab(), "Credits & Licenses")
        tabs.addTab(self._security_tab(), "Security")
        v.addWidget(tabs)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        v.addWidget(close)

    def _about_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("<h2>Paragraphos</h2>"))
        v.addWidget(
            QLabel(
                "Local podcast → whisper.cpp pipeline.<br>"
                f"Version {VERSION} · Apple Silicon only"
            )
        )
        v.addWidget(
            QLabel(
                "<br>The name <b>Paragraphos</b> refers to the ancient Greek "
                "punctuation mark that signalled a change of speaker in a text — "
                "the job Paragraphos does for every episode it transcribes."
            )
        )
        v.addWidget(
            QLabel(
                "<br><b>Technology</b>: Python 3.12, PyQt6, whisper.cpp "
                "(large-v3-turbo), APScheduler, watchdog, feedparser."
            )
        )
        v.addWidget(
            QLabel(
                "<br><b>Spotlight</b>: macOS automatically indexes the "
                "<code>.md</code> transcripts in your output folder. "
                "Search them system-wide with ⌘Space."
            )
        )
        v.addWidget(
            QLabel(
                "<br><b>Privacy</b>: everything runs locally. No cloud APIs "
                "for transcription. No telemetry."
            )
        )
        v.addStretch()
        return w

    def _licenses_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(
            QLabel(
                "Paragraphos stands on the shoulders of open-source projects. "
                "The full list of bundled + runtime dependencies and their licenses:"
            )
        )

        html = "<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>"
        html += (
            "<tr style='background:palette(alternate-base);'>"
            "<th align='left'>Component</th>"
            "<th align='left'>Version</th>"
            "<th align='left'>License</th>"
            "<th align='left'>Project</th></tr>"
        )
        for name, ver, lic, url in DEPENDENCIES:
            html += (
                "<tr>"
                f"<td><b>{name}</b></td>"
                f"<td>{ver}</td>"
                f"<td>{lic}</td>"
                f"<td><a href='{url}'>{url.replace('https://', '').rstrip('/')}</a></td>"
                "</tr>"
            )
        html += "</table>"

        html += (
            "<br><br>"
            "<b>About the licenses</b><br>"
            "MIT, BSD, Apache-2.0, and PSF are permissive — they allow "
            "free use, modification, and redistribution subject to "
            "attribution and preservation of the license notice. "
            "GPL / LGPL (PyQt6 under GPL-3.0, parts of ffmpeg under "
            "LGPL-2.1/GPL) require that modifications to those components "
            "themselves be released under the same license; dynamic "
            "linking from Paragraphos is covered. Paragraphos itself is "
            "a personal project and is not redistributed to third parties."
            "<br><br>"
            "<b>Whisper model weights</b> (OpenAI, released under MIT) "
            "are downloaded separately from the Hugging Face mirror at "
            "<a href='https://huggingface.co/ggerganov/whisper.cpp'>"
            "huggingface.co/ggerganov/whisper.cpp</a>."
            "<br><br>"
            "<b>Podcast audio</b> remains the property of its original "
            "authors. Transcripts are derived works for personal "
            "research / archiving use. Check the license of each podcast "
            "before redistribution."
        )

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        v.addWidget(browser)
        return w

    def _security_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        html = (
            "<h3>Threat model</h3>"
            "Paragraphos ingests <b>fully untrusted data</b>: RSS feed XML, "
            "episode landing-page HTML, MP3 URLs, and OPML subscription lists. "
            "A compromised feed or a MITM between you and a podcast host "
            "should not be able to read your local files, reach your private "
            "network, or execute code on your Mac."
            ""
            "<h3>Mitigations in place</h3>"
            "<ul>"
            "<li><b>URL allowlist</b> — only <code>http://</code> and "
            "<code>https://</code> are followed. <code>file://</code>, "
            "<code>data:</code>, <code>javascript:</code> are rejected.</li>"
            "<li><b>SSRF guard</b> — URLs resolving to loopback, link-local, "
            "private (RFC1918), multicast, or reserved IP ranges are refused, "
            "so a malicious feed can't probe your LAN or read "
            "<code>http://localhost/admin</code>.</li>"
            "<li><b>Download caps</b> — MP3 ≤ 2 GB, RSS feed ≤ 50 MB, "
            "HTML ≤ 10 MB. Streams exceeding the cap are aborted and the "
            "<code>.part</code> file deleted.</li>"
            "<li><b>Content-Type sniffing</b> — MP3 downloads must advertise "
            "<code>audio/*</code> or <code>application/octet-stream</code>. "
            "A feed can't sneak a <code>text/html</code> payload into your "
            "transcripts folder.</li>"
            "<li><b>XML hardening</b> — OPML parsing uses "
            "<code>defusedxml</code> (blocks XXE, billion-laughs, external "
            "entity expansion). feedparser and lxml are called without "
            "feature flags that enable entity resolution.</li>"
            "<li><b>Path-traversal defence</b> — the filename sanitizer "
            'strips <code>/ \\ : * ? " &lt; &gt; |</code> and neutralises '
            "<code>..</code>. A second check (<code>safe_path_within</code>) "
            "verifies each write stays inside <code>output_root</code>.</li>"
            "<li><b>Model integrity</b> — whisper-cpp GGML models are "
            "verified against a pinned SHA-256 after download; a mismatched "
            "file is deleted before being moved into place.</li>"
            "<li><b>No shell execution</b> — all subprocess invocations use "
            "<code>subprocess.run([...])</code> with list-form arguments. "
            "Episode titles, whisper prompts, and feed URLs never touch a "
            "shell. No <code>shell=True</code> anywhere.</li>"
            "<li><b>SQL injection impossible</b> — every state query uses "
            "parameterised <code>?</code> placeholders.</li>"
            "<li><b>YAML is <code>safe_load</code> only</b> — frontmatter "
            "parsing can't instantiate arbitrary Python classes.</li>"
            "</ul>"
            ""
            "<h3>Residual risks</h3>"
            "<ul>"
            "<li><b>whisper.cpp itself</b> is a C++ binary; a crafted MP3 "
            "could in theory exploit a parser bug. macOS sandbox / signed "
            "Homebrew releases mitigate this. Keep <code>brew upgrade "
            "whisper-cpp</code> current.</li>"
            "<li><b>HTTP-only feeds</b> (no TLS) are still followed — their "
            "contents can be tampered with on the wire. A future release "
            "could flag these in the feed-health check.</li>"
            "<li><b>No code signing / notarization</b> — the .app is locally "
            "ad-hoc signed, so macOS Gatekeeper warns on first launch. Only "
            "install Paragraphos from a source you trust.</li>"
            "</ul>"
            ""
            "<h3>Reporting a vulnerability</h3>"
            "Paragraphos is a personal project. If you find a security issue, "
            "open a private issue in the repository or mail the maintainer "
            "directly before disclosing publicly."
        )
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        v.addWidget(browser)
        return w


class ChangelogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragraphos Changelog")
        self.resize(640, 520)
        v = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        text = (
            CHANGELOG_PATH.read_text(encoding="utf-8")
            if CHANGELOG_PATH.exists()
            else "_No CHANGELOG.md found yet._"
        )
        browser.setMarkdown(text)
        v.addWidget(browser)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        v.addWidget(close)
