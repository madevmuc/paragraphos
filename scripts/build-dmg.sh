#!/usr/bin/env bash
# Build a distribution DMG containing Paragraphos.app.
#
# Usage:
#   .venv/bin/python setup-full.py py2app
#   ./scripts/build-dmg.sh [version]
#
# Defaults to v0.5.0 when no argument is given. Output: dist/Paragraphos-<version>.dmg

set -euo pipefail

VERSION="${1:-0.5.0}"
APP_NAME="Paragraphos"
APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="dist/${APP_NAME}-${VERSION}.dmg"
STAGING="dist/_dmg_staging"

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: $APP_PATH not found. Build with: .venv/bin/python setup-full.py py2app" >&2
  exit 1
fi

rm -rf "$STAGING" "$DMG_PATH"
mkdir -p "$STAGING"

# Copy app + convenient /Applications symlink.
cp -R "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "${APP_NAME} ${VERSION}" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGING"

echo "built: $DMG_PATH"
du -h "$DMG_PATH"
