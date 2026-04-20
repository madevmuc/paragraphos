import re
from pathlib import Path

from core.version import VERSION


REPO = Path(__file__).resolve().parent.parent


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?", VERSION), VERSION


def test_setup_bundle_versions_match():
    for name in ("setup.py", "setup-full.py", "setup-full-universal.py"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert f'"{VERSION}"' in text, f"{name} missing {VERSION}"


def test_pyproject_version_matches():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{VERSION}"' in text


def test_about_dialog_references_version():
    text = (REPO / "ui" / "about_dialog.py").read_text(encoding="utf-8")
    assert "from core.version import VERSION" in text
