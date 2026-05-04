"""Regression: the first-run wizard's `Install Homebrew…` script.

User-reported install loop: clicking Install Homebrew opened a
Terminal that printed

    curl: (77) error setting certificate verify locations:
      CAfile: /Applications/Paragraphos.app/Contents/Resources/openssl.ca/no-such-file
      CApath: /Applications/Paragraphos.app/Contents/Resources/openssl.ca/no-such-file
    ✓ Homebrew installer finished. Close this window and click Recheck in Paragraphos.

Two bugs in one script:

1. ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` / ``CURL_CA_BUNDLE`` /
   ``REQUESTS_CA_BUNDLE`` / ``OPENSSL_CONF`` env vars stuffed in by
   py2app for the bundled Python's TLS leak into the Terminal child;
   they point at non-existent paths inside the .app bundle and curl
   dies (exit 77).
2. The brew one-liner was ``/bin/bash -c "$(curl …)"``; when curl
   fails the substitution is empty, bash runs nothing successfully,
   ``set -e`` is satisfied, and the script prints "Homebrew
   installer finished" anyway.

These tests sniff the generated script text to pin both fixes so a
future refactor can't reintroduce the loop.
"""

from __future__ import annotations

import os
import subprocess

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app_ref = QApplication.instance() or QApplication([])


def _open_script(monkeypatch, tmp_path):
    """Patch out the QMessageBox + the actual ``open -a Terminal``
    call, run the wizard's ``_install_brew``, return the path of the
    generated .command script for inspection."""
    captured: dict = {}

    real_popen = subprocess.Popen

    def fake_popen(argv, *a, **kw):
        # Only intercept the wizard's `open -a Terminal …` call;
        # forward anything else (pytest internals etc.) to the real
        # Popen so collection still works.
        if (
            isinstance(argv, list)
            and argv
            and argv[0] == "open"
            and "-a" in argv
            and "Terminal" in argv
        ):
            captured["argv"] = argv
            captured["script_path"] = argv[-1]

            class _Proc:
                returncode = 0

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def wait(self, *a, **kw):
                    return 0

            return _Proc()
        return real_popen(argv, *a, **kw)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: 0))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))

    # FirstRunWizard's __init__ runs deps.check() — patch to a stub so
    # the test doesn't depend on the test machine's brew/whisper state.
    from core import deps as _deps
    from ui.first_run_wizard import FirstRunWizard

    monkeypatch.setattr(
        _deps,
        "check",
        lambda: type(
            "S",
            (),
            {
                "compatible_mac": True,
                "brew": False,
                "whisper_cli": False,
                "ffmpeg": False,
                "model": True,
            },
        )(),
    )

    wiz = FirstRunWizard(parent=None)
    wiz._install_brew()
    return captured["script_path"]


def test_brew_script_unsets_bundled_ssl_env(monkeypatch, tmp_path):
    """py2app's SSL_CERT_FILE / SSL_CERT_DIR / etc. point at paths inside
    the .app bundle that don't exist outside it. Inheriting them into
    the Terminal subprocess kills curl with exit 77. The script must
    unset them before any curl runs."""
    script_path = _open_script(monkeypatch, tmp_path)
    body = open(script_path).read()
    assert "unset" in body, "script must clear inherited TLS env vars"
    for var in (
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "REQUESTS_CA_BUNDLE",
        "OPENSSL_CONF",
    ):
        assert var in body, f"missing unset of {var}"


def test_brew_script_aborts_on_curl_failure(monkeypatch, tmp_path):
    """Pre-fix the script swallowed curl's exit code via
    `bash -c "$(curl …)"`, then printed "Homebrew installer finished"
    even when nothing was downloaded. Now the script must download
    install.sh via curl into a tempfile and check curl's status
    explicitly. Verified end-to-end by simulating a curl failure
    (PATH-prepend a fake curl that exits 77) and asserting the
    script propagates the failure as a non-zero exit and never
    prints the success line."""
    script_path = _open_script(monkeypatch, tmp_path)
    body = open(script_path).read()
    # Belt: the script must download into a file, not into a bash -c
    # substitution.
    assert "curl" in body
    assert '-o "$script"' in body or "-o $script" in body, "curl must write to a tempfile"
    # Suspenders: actually run the script with a fake curl that fails
    # and assert it exits non-zero without printing the success line.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/bin/sh\necho 'curl: (77) fake cert error' >&2\nexit 77\n")
    fake_curl.chmod(0o755)

    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}"}
    proc = subprocess.run(
        ["/bin/sh", script_path], capture_output=True, text=True, env=env, timeout=10
    )
    assert proc.returncode != 0, (
        f"curl failure must propagate to a non-zero script exit; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "Homebrew installer finished" not in proc.stdout, (
        "must NOT print success line when curl failed"
    )
