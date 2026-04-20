"""Full (non-alias) py2app build: standalone Paragraphos.app for any Mac.

Bundles Python + all site-packages into the .app (~400-600 MB). The resulting
bundle runs on a fresh Mac without needing the knowledge-hub repo or its
.venv. The first-run wizard installs the non-Python system dependencies
(Homebrew, whisper-cpp, ffmpeg, whisper model).

Build:
    cd scripts/paragraphos
    ../../.venv/bin/python setup-full.py py2app
    # Result: dist/Paragraphos.app (standalone)
    # Drag to /Applications or share as a .dmg.
"""

from setuptools import setup

from core.version import VERSION

APP = ["app.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Paragraphos",
        "CFBundleDisplayName": "Paragraphos",
        "CFBundleIdentifier": "com.m4ma.paragraphos",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "OPML Subscription File",
            "CFBundleTypeExtensions": ["opml", "xml"],
            "CFBundleTypeRole": "Viewer",
            "LSItemContentTypes": ["public.xml", "public.opml"],
            "LSHandlerRank": "Alternate",
        }],
    },
    "packages": [
        "core", "ui",
        # Third-party — py2app needs these explicit so hidden imports are found.
        "PyQt6", "apscheduler", "watchdog", "feedparser", "httpx",
        "yaml", "pydantic", "bs4", "lxml", "sniffio", "anyio",
        "h11", "httpcore", "pytz", "tzlocal", "defusedxml",
    ],
    "includes": [
        "scripts_legacy_shows",
        "pydantic_core",
        "pydantic.deprecated.decorator",
    ],
    "excludes": [
        "tkinter", "matplotlib", "pandas", "numpy", "scipy",
        "pytest", "respx", "IPython",
    ],
    "resources": ["CHANGELOG.md"],
}

setup(
    app=APP,
    name="Paragraphos",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
