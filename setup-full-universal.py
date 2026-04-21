"""Universal2 (arm64 + x86_64) py2app build.

Produces a fat .app that runs on both Apple Silicon and Intel Macs.
Every native dependency needs to be present as universal wheels — this
typically means:

  .venv/bin/pip install --upgrade --force-reinstall \\
    --platform macosx_11_0_universal2 \\
    --only-binary=:all: \\
    --target .venv-universal \\
    -r requirements.txt

Then run:

  .venv/bin/python setup-full-universal.py py2app
  ./scripts/build-dmg.sh 0.5.0-universal

Not tested on CI yet — Phase 5.22 will wire GitHub Actions. Intel Mac
users can build from source with the regular setup.py in the meantime.
"""

from setuptools import setup

from core.version import VERSION

APP = ["app.py"]
OPTIONS = {
    "argv_emulation": False,
    "arch": "universal2",
    "iconfile": "assets/AppIcon.icns",
    "plist": {
        "CFBundleName": "Paragraphos",
        "CFBundleDisplayName": "Paragraphos",
        "CFBundleIdentifier": "com.m4ma.paragraphos",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "OPML Subscription File",
                "CFBundleTypeExtensions": ["opml", "xml"],
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.xml", "public.opml"],
                "LSHandlerRank": "Alternate",
            }
        ],
    },
    "packages": [
        "core",
        "ui",
        "PyQt6",
        "apscheduler",
        "watchdog",
        "feedparser",
        "httpx",
        "yaml",
        "pydantic",
        "bs4",
        "lxml",
        "sniffio",
        "anyio",
        "h11",
        "httpcore",
        "pytz",
        "tzlocal",
        "defusedxml",
        "certifi",
    ],
    "includes": [
        "scripts_legacy_shows",
        "pydantic_core",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "pandas",
        "numpy",
        "scipy",
        "pytest",
        "respx",
        "IPython",
    ],
    "resources": ["CHANGELOG.md", "data/default_prompts.yaml"],
}

setup(
    app=APP,
    name="Paragraphos",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
