import re
from pathlib import Path

from core.version import VERSION


REPO = Path(__file__).resolve().parent.parent


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?", VERSION), VERSION


def test_setup_bundle_versions_match():
    """Each setup file must import VERSION from core.version and reference the
    symbol (not a hardcoded literal) in its plist entries — this is what keeps
    core/version.py the single source of truth across release bumps."""
    for name in ("setup.py", "setup-full.py", "setup-full-universal.py"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "from core.version import VERSION" in text, (
            f"{name} must import VERSION from core.version"
        )
        assert '"CFBundleVersion": VERSION' in text, (
            f"{name} must use the VERSION identifier for CFBundleVersion"
        )
        assert '"CFBundleShortVersionString": VERSION' in text, (
            f"{name} must use the VERSION identifier for CFBundleShortVersionString"
        )


def test_pyproject_version_matches():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{VERSION}"' in text


def test_about_dialog_references_version():
    text = (REPO / "ui" / "about_dialog.py").read_text(encoding="utf-8")
    assert "from core.version import VERSION" in text
