"""py2app build config for Paragraphos.

Build an alias-mode .app (fast, references current source tree):
    cd scripts/paragraphos
    ../../.venv/bin/python setup.py py2app -A
    open dist/Paragraphos.app

Alias mode is the right choice for personal use: the .app is just a thin
launcher pointing at this directory's code + the repo's .venv Python. Edits
to the source take effect next launch — no rebuild needed unless you add
new top-level dependencies.

For a standalone bundle you could drag onto another Mac, run without -A.
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
        "LSUIElement": False,  # Set True to hide Dock icon (menu-bar-only)
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
    "packages": ["core", "ui"],
    "includes": [
        "apscheduler", "watchdog", "feedparser", "httpx", "yaml",
        "pydantic", "bs4", "lxml",
    ],
}

setup(
    app=APP,
    name="Paragraphos",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
